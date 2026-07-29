import xml.etree.ElementTree as ET

import httpx

from app.providers.tts_azure import AzureTTS, _build_ssml


async def test_azure_adapter_sends_clean_ssml_and_returns_sentence_boundary():
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"synthetic-mp3")

    tts = AzureTTS(
        api_key="test-key",
        region="",
        endpoint="https://tts.example.test/custom/speech",
        transport=httpx.MockTransport(respond),
    )
    try:
        segment = await tts.synthesize("**A & B** [1]", "zh-CN-XiaoxiaoNeural")
    finally:
        await tts.aclose()

    assert segment.ok
    assert segment.audio == b"synthetic-mp3"
    assert segment.mime_type == "audio/mpeg"
    assert len(segment.visemes) == 1
    assert segment.visemes[0].duration_s == 0
    assert segment.visemes[0].text == "A & B"

    request = requests[0]
    assert str(request.url) == "https://tts.example.test/custom/speech"
    assert request.headers["ocp-apim-subscription-key"] == "test-key"
    assert request.headers["x-microsoft-outputformat"] == (
        "audio-24khz-48kbitrate-mono-mp3"
    )
    body = request.content.decode()
    assert "**" not in body and "[1]" not in body
    assert "A &amp; B" in body


async def test_azure_http_failure_degrades_without_raising():
    tts = AzureTTS(
        api_key="test-key",
        region="eastasia",
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
    )
    try:
        segment = await tts.synthesize("仍然显示这句字幕。", "zh-CN-XiaoxiaoNeural")
    finally:
        await tts.aclose()

    assert not segment.ok
    assert segment.audio == b""


async def test_azure_official_endpoint_is_derived_from_region():
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"synthetic-mp3")

    tts = AzureTTS(
        api_key="test-key",
        region="eastasia",
        transport=httpx.MockTransport(respond),
    )
    try:
        segment = await tts.synthesize("测试。", "zh-CN-XiaoxiaoNeural")
    finally:
        await tts.aclose()

    assert segment.ok
    assert str(requests[0].url) == (
        "https://eastasia.tts.speech.microsoft.com/cognitiveservices/v1"
    )


async def test_azure_network_failure_degrades_without_raising():
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    tts = AzureTTS(
        api_key="test-key",
        region="eastasia",
        transport=httpx.MockTransport(fail),
    )
    try:
        segment = await tts.synthesize("网络断开。", "zh-CN-XiaoxiaoNeural")
    finally:
        await tts.aclose()

    assert not segment.ok
    assert segment.audio == b""


async def test_empty_spoken_text_skips_the_provider_call():
    called = False

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, content=b"unexpected")

    tts = AzureTTS(
        api_key="test-key",
        region="eastasia",
        transport=httpx.MockTransport(respond),
    )
    try:
        segment = await tts.synthesize("[1] ***", "zh-CN-XiaoxiaoNeural")
    finally:
        await tts.aclose()

    assert segment.ok
    assert segment.audio == b""
    assert not called


def test_ssml_quotes_configured_voice_attributes():
    voice = 'zh-CN-Test" data-extra="unsafe'
    root = ET.fromstring(_build_ssml("A & B", voice))  # noqa: S314 - locally generated
    node = next(iter(root))

    assert node.attrib["name"] == voice
    assert node.text == "A & B"
