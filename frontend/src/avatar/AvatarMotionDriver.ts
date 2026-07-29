/**
 * Idle life: relaxed posture, breathing, blinking, gaze.
 *
 * Entirely procedural: no .vrma or mocap asset is shipped.
 *
 * Blink and saccade behaviour is adapted from pixiv/ChatVRM (MIT).
 */

import * as THREE from "three";
import { VRMExpressionPresetName, type VRM } from "@pixiv/three-vrm";

import type { AvatarExpression, AvatarState } from "./types";

const BLINK_CLOSE_S = 0.09;
const BLINK_OPEN_S = 0.12;
const BLINK_MIN_INTERVAL_S = 1.8;
const BLINK_MAX_INTERVAL_S = 6.0;

const SACCADE_MIN_INTERVAL_S = 1.2;
const SACCADE_MAX_INTERVAL_S = 4.5;

const EMOTION_ATTACK = 0.12;

type PosedBone = {
  node: THREE.Object3D;
  baseRotation: THREE.Quaternion;
};

const RELAXED_ARM_POSE = [
  ["leftUpperArm", 0, -0.08, 1.18],
  ["rightUpperArm", 0, 0.06, -1.12],
  ["leftLowerArm", 0, -0.18, 0.16],
  ["rightLowerArm", 0, 0.14, -0.13],
] as const;

export class AvatarMotionDriver {
  private readonly gazeTarget = new THREE.Object3D();
  private readonly gazeGoal = new THREE.Vector3(0, 0, -1);

  private chest: THREE.Object3D | null = null;
  private hips: THREE.Object3D | null = null;
  private chestBaseRotationX = 0;
  private hipsBasePositionY = 0;
  private hipsBaseRotationZ = 0;
  private posedBones: PosedBone[] = [];

  private blinkTimer = 2;
  private blinkPhase: "open" | "closing" | "opening" = "open";
  private blinkProgress = 0;

  private saccadeTimer = 1;

  private expression: AvatarExpression = "neutral";
  private readonly weights: Record<AvatarExpression, number> = {
    neutral: 1,
    happy: 0,
    angry: 0,
    sad: 0,
    relaxed: 0,
    surprised: 0,
  };

  private elapsed = 0;

  attach(vrm: VRM, camera: THREE.Camera): void {
    this.restorePose();
    this.chest =
      vrm.humanoid.getNormalizedBoneNode("upperChest") ??
      vrm.humanoid.getNormalizedBoneNode("chest") ??
      vrm.humanoid.getNormalizedBoneNode("spine");
    this.hips = vrm.humanoid.getNormalizedBoneNode("hips");
    this.chestBaseRotationX = this.chest?.rotation.x ?? 0;
    this.hipsBasePositionY = this.hips?.position.y ?? 0;
    this.hipsBaseRotationZ = this.hips?.rotation.z ?? 0;
    this.applyRelaxedPose(vrm);

    camera.add(this.gazeTarget);
    this.gazeTarget.position.set(0, 0, -1);
    if (vrm.lookAt) {
      vrm.lookAt.target = this.gazeTarget;
      vrm.lookAt.autoUpdate = true;
    }
  }

  private applyRelaxedPose(vrm: VRM): void {
    for (const [boneName, x, y, z] of RELAXED_ARM_POSE) {
      const node = vrm.humanoid.getNormalizedBoneNode(boneName);
      if (!node) continue;

      const baseRotation = node.quaternion.clone();
      const offset = new THREE.Quaternion().setFromEuler(new THREE.Euler(x, y, z));
      node.quaternion.copy(baseRotation).multiply(offset);
      this.posedBones.push({ node, baseRotation });
    }
  }

  private restorePose(): void {
    for (const { node, baseRotation } of this.posedBones) {
      node.quaternion.copy(baseRotation);
    }
    this.posedBones = [];
  }

  setExpression(expression: AvatarExpression): void {
    this.expression = expression;
  }

  update(vrm: VRM, delta: number, state: AvatarState): void {
    this.elapsed += delta;
    const manager = vrm.expressionManager;
    if (!manager) return;

    this.updateBreathing(state);
    this.updateGaze(delta, state);

    manager.setValue(VRMExpressionPresetName.Blink, this.updateBlink(delta, state));

    for (const key of Object.keys(this.weights) as AvatarExpression[]) {
      const goal = key === this.expression ? 1 : 0;
      this.weights[key] += (goal - this.weights[key]) * EMOTION_ATTACK;
      if (key !== "neutral") {
        manager.setValue(key, this.weights[key]);
      }
    }
  }

  /** Subtle chest rise and weight shift so the model never looks frozen. */
  private updateBreathing(state: AvatarState): void {
    // Thinking breathes a little faster; speaking a little deeper.
    const rate = state === "thinking" ? 0.45 : 0.32;
    const depth = state === "speaking" ? 0.022 : 0.015;

    const breath = Math.sin(this.elapsed * Math.PI * 2 * rate);
    if (this.chest) {
      this.chest.rotation.x = this.chestBaseRotationX + breath * depth;
    }
    if (this.hips) {
      this.hips.position.y = this.hipsBasePositionY + breath * 0.004;
      this.hips.rotation.z =
        this.hipsBaseRotationZ + Math.sin(this.elapsed * 0.37) * 0.012;
    }
  }

  private updateGaze(delta: number, state: AvatarState): void {
    this.saccadeTimer -= delta;
    if (this.saccadeTimer <= 0) {
      this.saccadeTimer = randomBetween(SACCADE_MIN_INTERVAL_S, SACCADE_MAX_INTERVAL_S);
      // While speaking the gaze stays closer to the viewer — looking away
      // mid-sentence reads as evasive.
      const spread = state === "speaking" ? 0.12 : 0.3;
      this.gazeGoal.set(
        (Math.random() - 0.5) * spread,
        (Math.random() - 0.5) * spread * 0.6,
        -1,
      );
    }
    this.gazeTarget.position.lerp(this.gazeGoal, Math.min(1, delta * 3.5));
  }

  private updateBlink(delta: number, state: AvatarState): number {
    if (state === "error") return 0.85; // half-lidded reads as "something is wrong"

    switch (this.blinkPhase) {
      case "open":
        this.blinkTimer -= delta;
        if (this.blinkTimer <= 0) {
          this.blinkPhase = "closing";
          this.blinkProgress = 0;
        }
        return 0;

      case "closing":
        this.blinkProgress += delta / BLINK_CLOSE_S;
        if (this.blinkProgress >= 1) {
          this.blinkPhase = "opening";
          this.blinkProgress = 0;
          return 1;
        }
        return this.blinkProgress;

      case "opening":
        this.blinkProgress += delta / BLINK_OPEN_S;
        if (this.blinkProgress >= 1) {
          this.blinkPhase = "open";
          this.blinkTimer = randomBetween(BLINK_MIN_INTERVAL_S, BLINK_MAX_INTERVAL_S);
          return 0;
        }
        return 1 - this.blinkProgress;
    }
  }

  dispose(camera: THREE.Camera): void {
    camera.remove(this.gazeTarget);
    this.restorePose();
    this.chest = null;
    this.hips = null;
  }
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min);
}
