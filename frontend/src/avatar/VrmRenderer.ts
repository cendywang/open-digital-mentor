/**
 * The VRM implementation of `AvatarRuntime`.
 *
 * Owns three.js, the VRM, the audio graph and the render loop — and nothing
 * else. It has never heard of retrieval, citations or the mentor.
 *
 * The renderer uses three-point lighting and offers an opt-in MToon→PBR
 * conversion (`renderPreset`), because the conversion does not suit every
 * model.
 */

import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import {
  VRMExpressionPresetName,
  VRMLoaderPlugin,
  VRMUtils,
  type VRM,
} from "@pixiv/three-vrm";

import { AvatarMotionDriver } from "./AvatarMotionDriver";
import { LipSyncDriver } from "./LipSyncDriver";
import type {
  AvatarAttribution,
  AvatarExpression,
  AvatarRuntime,
  AvatarState,
  SpeakRequest,
} from "./types";

export type RenderPreset = "stylized" | "pbr";

export interface VrmRendererOptions {
  renderPreset?: RenderPreset;
}

export class VrmRenderer implements AvatarRuntime {
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(24, 1, 0.1, 20);
  private readonly timer = new THREE.Timer();
  private readonly motion = new AvatarMotionDriver();
  private readonly listeners = new Set<(state: AvatarState) => void>();
  private readonly renderPreset: RenderPreset;

  private renderer: THREE.WebGLRenderer | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private resizeObserver: ResizeObserver | null = null;
  private frame = 0;

  private vrm: VRM | null = null;
  private _state: AvatarState = "loading";
  private loadFailed = false;

  private audioContext: AudioContext | null = null;
  private lipSync: LipSyncDriver | null = null;
  private source: AudioBufferSourceNode | null = null;
  private resolvePlayback: (() => void) | null = null;

  constructor(options: VrmRendererOptions = {}) {
    this.renderPreset = options.renderPreset ?? "stylized";
  }

  get state(): AvatarState {
    return this._state;
  }

  // -- lifecycle ----------------------------------------------------------

  mount(canvas: HTMLCanvasElement): void {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;

    this.setupLighting();
    this.timer.connect(document);
    this.camera.position.set(0, 1.32, 1.5);
    this.camera.lookAt(0, 1.28, 0);
    this.scene.add(this.camera);

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas.parentElement ?? canvas);
    this.resize();

    this.loop();
  }

  async load(url: string): Promise<void> {
    this.loadFailed = false;
    this.setState("loading");

    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));

    try {
      const gltf = await loader.loadAsync(url);
      const vrm = gltf.userData.vrm as VRM | undefined;
      if (!vrm) throw new Error("file loaded but contains no VRM extension");

      // Perf hygiene recommended by three-vrm: fewer skeletons and morph
      // targets, which matters a lot on mobile GPUs.
      VRMUtils.combineSkeletons(vrm.scene);
      VRMUtils.combineMorphs(vrm);
      VRMUtils.rotateVRM0(vrm);

      vrm.scene.traverse((object) => {
        object.frustumCulled = false;
      });

      if (this.renderPreset === "pbr") {
        convertToPBR(vrm);
      }

      this.disposeVrm();
      this.vrm = vrm;
      this.scene.add(vrm.scene);
      this.motion.attach(vrm, this.camera);

      this.frameCameraOnHead(vrm);
      this.setState("idle");
    } catch (error) {
      // A missing or corrupt model must not take the app down: text Q&A and
      // citations keep working with no avatar at all.
      console.error("[avatar] failed to load VRM:", error);
      this.loadFailed = true;
      this.setState("error");
      throw error;
    }
  }

  dispose(): void {
    cancelAnimationFrame(this.frame);
    this.resizeObserver?.disconnect();
    this.stop();
    this.motion.dispose(this.camera);
    this.timer.dispose();
    this.disposeVrm();
    void this.audioContext?.close();
    this.audioContext = null;
    this.renderer?.dispose();
    this.renderer = null;
    this.listeners.clear();
  }

  // -- state --------------------------------------------------------------

  setState(state: AvatarState): void {
    // Once loading has failed there is no avatar whose thinking/speaking
    // state could be shown. Keep the visible degradation notice in place
    // while text, citations and audio continue independently.
    if (this.loadFailed && state !== "loading" && state !== "error") return;
    if (this._state === state) return;
    this._state = state;
    for (const listener of this.listeners) listener(state);
  }

  onStateChange(listener: (state: AvatarState) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  setExpression(expression: AvatarExpression): void {
    this.motion.setExpression(expression);
  }

  getAttribution(): AvatarAttribution | null {
    const meta = this.vrm?.meta as Record<string, unknown> | undefined;
    if (!meta) return null;
    const authors = meta.authors as string[] | undefined;
    return {
      title: (meta.name ?? meta.title) as string | undefined,
      author: authors?.join(", ") ?? (meta.author as string | undefined),
      license: (meta.licenseName ?? meta.licenseUrl) as string | undefined,
      otherLicenseUrl: (meta.otherLicenseUrl ?? meta.thirdPartyLicenses) as string | undefined,
    };
  }

  // -- audio --------------------------------------------------------------

  async speak(request: SpeakRequest): Promise<void> {
    if (request.audio.byteLength === 0) return;

    const context = this.ensureAudioContext();
    if (context.state === "suspended") {
      await context.resume();
    }

    let buffer: AudioBuffer;
    try {
      buffer = await context.decodeAudioData(request.audio.slice(0));
    } catch (error) {
      console.warn("[avatar] undecodable audio, skipping segment:", error);
      return;
    }

    this.stopSource();

    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.lipSync!.node);

    this.source = source;
    this.setState("speaking");
    this.lipSync!.begin(request.visemes, context.currentTime);

    await new Promise<void>((resolve) => {
      this.resolvePlayback = resolve;
      source.onended = () => this.finishPlayback();
      source.start();
    });
  }

  stop(): void {
    this.stopSource();
    this.lipSync?.end();
    this.applyMouth(0, 0, 0);
    if (this._state === "speaking") {
      this.setState("idle");
    }
  }

  private stopSource(): void {
    const source = this.source;
    this.source = null;
    if (source) {
      source.onended = null;
      try {
        source.stop();
      } catch {
        // already stopped — fine
      }
      source.disconnect();
    }
    // Always settle the pending promise so a Stop can never deadlock the
    // audio queue waiting on a segment that will never end.
    this.resolvePlayback?.();
    this.resolvePlayback = null;
  }

  private finishPlayback(): void {
    this.source = null;
    this.lipSync?.end();
    this.applyMouth(0, 0, 0);
    this.resolvePlayback?.();
    this.resolvePlayback = null;
    if (this._state === "speaking") {
      this.setState("idle");
    }
  }

  private ensureAudioContext(): AudioContext {
    if (!this.audioContext) {
      this.audioContext = new AudioContext();
      this.lipSync = new LipSyncDriver(this.audioContext);
      this.lipSync.node.connect(this.audioContext.destination);
    }
    return this.audioContext;
  }

  // -- rendering ----------------------------------------------------------

  private setupLighting(): void {
    // Classic three-point rig: it is what makes a flat toon model read as a
    // person on a video call rather than as a game asset.
    const key = new THREE.DirectionalLight(0xffffff, 2.1);
    key.position.set(1.4, 2.0, 1.8);

    const fill = new THREE.DirectionalLight(0xdce8ff, 0.75);
    fill.position.set(-1.8, 1.2, 1.1);

    const rim = new THREE.DirectionalLight(0xffffff, 1.35);
    rim.position.set(-0.6, 1.9, -2.2);

    this.scene.add(key, fill, rim, new THREE.AmbientLight(0xffffff, 0.55));
  }

  private frameCameraOnHead(vrm: VRM): void {
    const head = vrm.humanoid.getNormalizedBoneNode("head");
    if (!head) return;
    const position = new THREE.Vector3();
    head.getWorldPosition(position);
    this.camera.position.set(position.x, position.y + 0.04, position.z + 1.45);
    this.camera.lookAt(position.x, position.y, position.z);
  }

  private resize(): void {
    if (!this.renderer || !this.canvas) return;
    const host = this.canvas.parentElement ?? this.canvas;
    const width = host.clientWidth || 1;
    const height = host.clientHeight || 1;
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }

  private loop = (timestamp?: number): void => {
    this.frame = requestAnimationFrame(this.loop);
    this.timer.update(timestamp);
    const delta = Math.min(this.timer.getDelta(), 0.1);
    const vrm = this.vrm;

    if (vrm) {
      this.motion.update(vrm, delta, this._state);

      if (this.source && this.lipSync && this.audioContext) {
        const mouth = this.lipSync.sample(this.audioContext.currentTime);
        this.applyMouth(mouth.aa, mouth.ih, mouth.ou);
      }

      // Spring bones read bone world matrices, so the skeleton has to be
      // settled before vrm.update runs — otherwise hair and skirts lag a
      // frame behind the body and visibly tear during head turns.
      vrm.scene.updateMatrixWorld(true);
      vrm.update(delta);
    }

    this.renderer?.render(this.scene, this.camera);
  };

  private applyMouth(aa: number, ih: number, ou: number): void {
    const manager = this.vrm?.expressionManager;
    if (!manager) return;
    manager.setValue(VRMExpressionPresetName.Aa, aa);
    manager.setValue(VRMExpressionPresetName.Ih, ih);
    manager.setValue(VRMExpressionPresetName.Ou, ou);
  }

  private disposeVrm(): void {
    if (!this.vrm) return;
    this.scene.remove(this.vrm.scene);
    VRMUtils.deepDispose(this.vrm.scene);
    this.vrm = null;
  }
}

/**
 * Replace MToon with MeshStandardMaterial.
 *
 * Trades the model's authored cel shading for photographic lighting response.
 * On a stylised character it can look like plastic, which is why this is a
 * preset and not the default.
 */
function convertToPBR(vrm: VRM): void {
  const replace = (material: THREE.Material): THREE.Material => {
    const source = material as THREE.Material & {
      map?: THREE.Texture;
      color?: THREE.Color;
      transparent?: boolean;
      alphaTest?: number;
      name: string;
    };

    const name = source.name.toLowerCase();
    const isSkin = name.includes("skin") || name.includes("face") || name.includes("body");
    const isHair = name.includes("hair");
    const isEye = name.includes("eye") || name.includes("iris") || name.includes("highlight");

    const standard = new THREE.MeshStandardMaterial({
      map: source.map,
      color: source.color?.clone() ?? new THREE.Color(0xffffff),
      transparent: source.transparent ?? false,
      alphaTest: source.alphaTest ?? 0,
      roughness: isEye ? 0.12 : isSkin ? 0.68 : isHair ? 0.42 : 0.6,
      metalness: 0,
      side: THREE.FrontSide,
    });
    standard.name = source.name;
    return standard;
  };

  vrm.scene.traverse((object) => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh) return;
    mesh.material = Array.isArray(mesh.material)
      ? mesh.material.map(replace)
      : replace(mesh.material);
  });
}
