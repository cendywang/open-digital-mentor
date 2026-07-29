import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

import sharp from "sharp";

const JSON_CHUNK = 0x4e4f534a;
const BIN_CHUNK = 0x004e4942;
const MAX_TEXTURE_EDGE = 512;

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath || inputPath === outputPath) {
  console.error(
    "usage: node scripts/optimize-vrm.mjs <source.vrm> <output.vrm>\n" +
      "source and output must be different paths",
  );
  process.exit(2);
}

const source = await readFile(inputPath);
const { json, binary } = parseGlb(source);
const originalBufferViews = json.bufferViews;

if (!Array.isArray(json.accessors) || !Array.isArray(originalBufferViews)) {
  throw new Error("VRM has no accessors or bufferViews");
}

const morphStats = pruneMorphTargets(json);
const imagePayloads = await resizeImages(json, originalBufferViews, binary);
const accessorStats = compactAccessors(json);
const { binary: compactBinary, bufferViewCount } = compactBufferViews(
  json,
  originalBufferViews,
  binary,
  imagePayloads,
);

if (!Array.isArray(json.buffers) || json.buffers.length !== 1) {
  throw new Error("optimizer supports a single embedded GLB buffer");
}
json.buffers[0] = { ...json.buffers[0], byteLength: compactBinary.length };
delete json.buffers[0].uri;

const output = buildGlb(json, compactBinary);
await mkdir(dirname(outputPath), { recursive: true });
await writeFile(outputPath, output);

console.log(`source       ${formatBytes(source.length)}`);
console.log(`output       ${formatBytes(output.length)}`);
console.log(`reduction    ${((1 - output.length / source.length) * 100).toFixed(1)}%`);
console.log(`textures     ${imagePayloads.resized}/${json.images?.length ?? 0} resized`);
console.log(`morph targets ${morphStats.before} -> ${morphStats.after}`);
console.log(`accessors    ${accessorStats.before} -> ${accessorStats.after}`);
console.log(`bufferViews  ${originalBufferViews.length} -> ${bufferViewCount}`);

function parseGlb(buffer) {
  if (buffer.length < 28 || buffer.toString("ascii", 0, 4) !== "glTF") {
    throw new Error("input is not a binary glTF/VRM file");
  }
  if (buffer.readUInt32LE(4) !== 2) {
    throw new Error(`unsupported glTF version ${buffer.readUInt32LE(4)}`);
  }

  const jsonLength = buffer.readUInt32LE(12);
  if (buffer.readUInt32LE(16) !== JSON_CHUNK) {
    throw new Error("first GLB chunk is not JSON");
  }
  const jsonEnd = 20 + jsonLength;
  const binLength = buffer.readUInt32LE(jsonEnd);
  if (buffer.readUInt32LE(jsonEnd + 4) !== BIN_CHUNK) {
    throw new Error("second GLB chunk is not BIN");
  }

  return {
    json: JSON.parse(buffer.subarray(20, jsonEnd).toString("utf8").trimEnd()),
    binary: buffer.subarray(jsonEnd + 8, jsonEnd + 8 + binLength),
  };
}

function pruneMorphTargets(json) {
  const groups = json.extensions?.VRM?.blendShapeMaster?.blendShapeGroups ?? [];
  const referenced = new Map();
  for (const group of groups) {
    for (const bind of group.binds ?? []) {
      if (!Number.isInteger(bind.mesh) || !Number.isInteger(bind.index)) continue;
      const indices = referenced.get(bind.mesh) ?? new Set();
      indices.add(bind.index);
      referenced.set(bind.mesh, indices);
    }
  }

  let before = 0;
  let after = 0;
  for (const [meshIndex, mesh] of (json.meshes ?? []).entries()) {
    const targetCount = Math.max(
      0,
      ...mesh.primitives.map((primitive) => primitive.targets?.length ?? 0),
    );
    if (targetCount === 0) continue;
    before += targetCount;

    const used = referenced.get(meshIndex);
    const keep = used ? [...used].sort((a, b) => a - b) : range(targetCount);
    if (keep.some((index) => index < 0 || index >= targetCount)) {
      throw new Error(`VRM expression references an invalid target on mesh ${meshIndex}`);
    }
    after += keep.length;
    const targetMap = new Map(keep.map((oldIndex, newIndex) => [oldIndex, newIndex]));

    for (const primitive of mesh.primitives) {
      if (!primitive.targets) continue;
      if (primitive.targets.length !== targetCount) {
        throw new Error(`mesh ${meshIndex} primitives have inconsistent morph target counts`);
      }
      primitive.targets = keep.map((oldIndex) => {
        const position = primitive.targets[oldIndex]?.POSITION;
        if (!Number.isInteger(position)) {
          throw new Error(`mesh ${meshIndex} target ${oldIndex} has no POSITION accessor`);
        }
        return { POSITION: position };
      });
    }

    if (Array.isArray(mesh.weights)) mesh.weights = keep.map((index) => mesh.weights[index]);
    if (Array.isArray(mesh.extras?.targetNames)) {
      mesh.extras.targetNames = keep.map((index) => mesh.extras.targetNames[index]);
    }
    for (const node of json.nodes ?? []) {
      if (node.mesh === meshIndex && Array.isArray(node.weights)) {
        node.weights = keep.map((index) => node.weights[index]);
      }
    }
    for (const group of groups) {
      for (const bind of group.binds ?? []) {
        if (bind.mesh !== meshIndex) continue;
        const remapped = targetMap.get(bind.index);
        if (remapped === undefined) {
          throw new Error(`failed to retain target ${bind.index} on mesh ${meshIndex}`);
        }
        bind.index = remapped;
      }
    }
  }
  return { before, after };
}

async function resizeImages(json, bufferViews, binary) {
  const payloads = new Map();
  let resized = 0;

  for (const [imageIndex, image] of (json.images ?? []).entries()) {
    if (!Number.isInteger(image.bufferView)) {
      throw new Error(`image ${imageIndex} is external; only embedded images are supported`);
    }
    const view = bufferViews[image.bufferView];
    if (!view) throw new Error(`image ${imageIndex} has an invalid bufferView`);
    const start = view.byteOffset ?? 0;
    const input = binary.subarray(start, start + view.byteLength);
    const metadata = await sharp(input).metadata();
    const width = metadata.width ?? 0;
    const height = metadata.height ?? 0;

    let output = input;
    if (Math.max(width, height) > MAX_TEXTURE_EDGE) {
      output = await sharp(input)
        .resize({
          width: MAX_TEXTURE_EDGE,
          height: MAX_TEXTURE_EDGE,
          fit: "inside",
          withoutEnlargement: true,
        })
        .png({ compressionLevel: 9, adaptiveFiltering: true, effort: 10 })
        .toBuffer();
      image.mimeType = "image/png";
      resized += 1;
    }
    payloads.set(image.bufferView, output);
  }

  payloads.resized = resized;
  return payloads;
}

function compactAccessors(json) {
  const used = new Set();
  const mark = (value) => {
    if (Number.isInteger(value)) used.add(value);
  };

  for (const mesh of json.meshes ?? []) {
    for (const primitive of mesh.primitives) {
      mark(primitive.indices);
      Object.values(primitive.attributes ?? {}).forEach(mark);
      for (const target of primitive.targets ?? []) Object.values(target).forEach(mark);
    }
  }
  for (const skin of json.skins ?? []) mark(skin.inverseBindMatrices);
  for (const animation of json.animations ?? []) {
    for (const sampler of animation.samplers ?? []) {
      mark(sampler.input);
      mark(sampler.output);
    }
  }

  const before = json.accessors.length;
  const kept = [...used].sort((a, b) => a - b);
  const map = new Map(kept.map((oldIndex, newIndex) => [oldIndex, newIndex]));
  const remap = (oldIndex) => {
    if (!Number.isInteger(oldIndex)) return oldIndex;
    const newIndex = map.get(oldIndex);
    if (newIndex === undefined) throw new Error(`accessor ${oldIndex} was not retained`);
    return newIndex;
  };

  for (const mesh of json.meshes ?? []) {
    for (const primitive of mesh.primitives) {
      if (Number.isInteger(primitive.indices)) primitive.indices = remap(primitive.indices);
      for (const key of Object.keys(primitive.attributes ?? {})) {
        primitive.attributes[key] = remap(primitive.attributes[key]);
      }
      for (const target of primitive.targets ?? []) {
        for (const key of Object.keys(target)) target[key] = remap(target[key]);
      }
    }
  }
  for (const skin of json.skins ?? []) {
    if (Number.isInteger(skin.inverseBindMatrices)) {
      skin.inverseBindMatrices = remap(skin.inverseBindMatrices);
    }
  }
  for (const animation of json.animations ?? []) {
    for (const sampler of animation.samplers ?? []) {
      sampler.input = remap(sampler.input);
      sampler.output = remap(sampler.output);
    }
  }

  json.accessors = kept.map((index) => json.accessors[index]);
  return { before, after: json.accessors.length };
}

function compactBufferViews(json, oldViews, originalBinary, imagePayloads) {
  const used = new Set();
  walk(json, (key, value) => {
    if (key === "bufferView" && Number.isInteger(value)) used.add(value);
  });

  const kept = [...used].sort((a, b) => a - b);
  const map = new Map(kept.map((oldIndex, newIndex) => [oldIndex, newIndex]));
  const parts = [];
  const newViews = [];
  let offset = 0;

  for (const oldIndex of kept) {
    const oldView = oldViews[oldIndex];
    if (!oldView) throw new Error(`invalid bufferView ${oldIndex}`);
    const padding = align4(offset) - offset;
    if (padding) {
      parts.push(Buffer.alloc(padding));
      offset += padding;
    }
    const start = oldView.byteOffset ?? 0;
    const payload =
      imagePayloads.get(oldIndex) ??
      originalBinary.subarray(start, start + oldView.byteLength);
    newViews.push({
      ...oldView,
      buffer: 0,
      byteOffset: offset,
      byteLength: payload.length,
    });
    parts.push(payload);
    offset += payload.length;
  }

  const finalPadding = align4(offset) - offset;
  if (finalPadding) parts.push(Buffer.alloc(finalPadding));
  json.bufferViews = newViews;
  walk(json, (key, value, parent) => {
    if (key !== "bufferView" || !Number.isInteger(value)) return;
    const remapped = map.get(value);
    if (remapped === undefined) throw new Error(`bufferView ${value} was not retained`);
    parent[key] = remapped;
  });

  return { binary: Buffer.concat(parts), bufferViewCount: newViews.length };
}

function buildGlb(json, binary) {
  const jsonSource = Buffer.from(JSON.stringify(json), "utf8");
  const jsonPadding = align4(jsonSource.length) - jsonSource.length;
  const jsonChunk = Buffer.concat([jsonSource, Buffer.alloc(jsonPadding, 0x20)]);
  const totalLength = 12 + 8 + jsonChunk.length + 8 + binary.length;
  const result = Buffer.alloc(totalLength);

  result.write("glTF", 0, "ascii");
  result.writeUInt32LE(2, 4);
  result.writeUInt32LE(totalLength, 8);
  result.writeUInt32LE(jsonChunk.length, 12);
  result.writeUInt32LE(JSON_CHUNK, 16);
  jsonChunk.copy(result, 20);
  const binHeader = 20 + jsonChunk.length;
  result.writeUInt32LE(binary.length, binHeader);
  result.writeUInt32LE(BIN_CHUNK, binHeader + 4);
  binary.copy(result, binHeader + 8);
  return result;
}

function walk(value, visitor) {
  if (!value || typeof value !== "object") return;
  for (const [key, child] of Object.entries(value)) {
    visitor(key, child, value);
    walk(child, visitor);
  }
}

function align4(value) {
  return Math.ceil(value / 4) * 4;
}

function range(length) {
  return Array.from({ length }, (_, index) => index);
}

function formatBytes(bytes) {
  return `${bytes.toLocaleString("en-US")} bytes (${(bytes / 1024 / 1024).toFixed(2)} MiB)`;
}
