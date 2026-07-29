// Runtime compatibility check for R-01: does the reference VRM actually parse
// and expose humanoid / expressions / springbones under three 0.185 + three-vrm 3.5.5?
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

// Minimal DOM shim so GLTFLoader's texture path doesn't explode in Node.
globalThis.self = globalThis;
globalThis.window = globalThis;
globalThis.createImageBitmap = undefined;
globalThis.URL.createObjectURL = () => "blob:stub";
globalThis.URL.revokeObjectURL = () => {};
globalThis.document = {
  createElementNS: (_ns, name) => {
    if (name === "img") {
      const img = { width: 4, height: 4, addEventListener(t, f) { if (t === "load") setTimeout(f, 0); }, removeEventListener() {}, set src(_v) {} };
      return img;
    }
    if (name === "canvas") {
      return { width: 4, height: 4, getContext: () => ({ drawImage() {}, getImageData: () => ({ data: new Uint8ClampedArray(64) }) }) };
    }
    return {};
  },
  createElement: (name) => globalThis.document.createElementNS(null, name),
};

const require = createRequire(import.meta.url);
const THREE = await import("three");
const { GLTFLoader } = await import("three/examples/jsm/loaders/GLTFLoader.js");
const { VRMLoaderPlugin, VRMUtils } = await import("@pixiv/three-vrm");

console.log("three:", THREE.REVISION, " three-vrm:", require("@pixiv/three-vrm/package.json").version);

const data = readFileSync(process.argv[2]);
const maxBytes = 5 * 1024 * 1024;
console.log("file size:", `${(data.length / 1024 / 1024).toFixed(2)} MiB`, data.length < maxBytes ? "✓" : "FAIL (must be < 5 MiB)");
const buffer = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);

const loader = new GLTFLoader();
loader.register((parser) => new VRMLoaderPlugin(parser));

const gltf = await new Promise((resolve, reject) =>
  loader.parse(buffer, "", resolve, reject)
);

const vrm = gltf.userData.vrm;
if (!vrm) { console.error("FAIL: no VRM extension found"); process.exit(1); }

console.log("VRM parsed ✓");
console.log("  meta.name        :", vrm.meta?.name ?? vrm.meta?.title);
console.log("  meta.licenseName :", vrm.meta?.licenseName ?? vrm.meta?.licenseUrl);
console.log("  meta.authors     :", vrm.meta?.authors ?? vrm.meta?.author);

const bones = ["hips","spine","chest","upperChest","head","neck","leftHand","rightHand","leftFoot"];
const found = bones.filter((b) => vrm.humanoid?.getNormalizedBoneNode(b));
console.log("  humanoid bones   :", `${found.length}/${bones.length}`, found.join(","));

const expressions = ["aa","ih","ou","blink","happy","angry","sad","relaxed","neutral"];
const haveExpr = expressions.filter((e) => vrm.expressionManager?.getExpression(e));
console.log("  expressions      :", `${haveExpr.length}/${expressions.length}`, haveExpr.join(","));

console.log("  springBoneManager:", vrm.springBoneManager ? `yes (${vrm.springBoneManager.joints.size} joints)` : "none");
console.log("  lookAt           :", vrm.lookAt ? "yes" : "none");

// The exact calls VrmRenderer makes at load time.
VRMUtils.combineSkeletons(vrm.scene);
VRMUtils.combineMorphs(vrm);
VRMUtils.rotateVRM0(vrm);
console.log("  VRMUtils combineSkeletons/combineMorphs/rotateVRM0 ✓");

// Drive the same calls the render loop makes.
vrm.expressionManager?.setValue("aa", 0.6);
vrm.expressionManager?.setValue("blink", 1.0);
for (let i = 0; i < 60; i++) { vrm.scene.updateMatrixWorld(true); vrm.update(1 / 60); }
console.log("  60 frames of vrm.update() ✓");

const ok = data.length < maxBytes && found.length >= 7 && haveExpr.length >= 6;
console.log(ok ? "\nRESULT: PASS — renderer API surface is compatible" : "\nRESULT: FAIL");
process.exit(ok ? 0 : 1);
