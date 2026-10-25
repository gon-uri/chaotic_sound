/** Rotating 3D view of an attractor, computed with the engine core (same as the sound). */

import { attractorPoints } from "@chaotic-sound/engine";
import { OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { type ReactNode, useMemo } from "react";
import * as THREE from "three";
import { catalog } from "../store/catalog.ts";

export function Attractor3D({ system, u }: { system: string; u: number }): ReactNode {
  const line = useMemo(() => {
    const a = attractorPoints(catalog, system, u, 20_000);
    const n = a.count;
    const pos = new Float32Array(n * 3);
    // Duffing's third variable is a phase: show (x, y, sin z) instead.
    const phase = system === "duffing";
    for (let i = 0; i < n; i++) {
      pos[3 * i] = a.points[a.dim * i]!;
      pos[3 * i + 1] = a.points[a.dim * i + 1]!;
      pos[3 * i + 2] = phase ? Math.sin(a.points[a.dim * i + 2]!) : a.points[a.dim * i + 2]!;
    }
    // Centre the bounding box at the origin and scale it into [-1, 1].
    const lo = [Infinity, Infinity, Infinity];
    const hi = [-Infinity, -Infinity, -Infinity];
    for (let i = 0; i < n; i++) {
      for (let k = 0; k < 3; k++) {
        lo[k] = Math.min(lo[k]!, pos[3 * i + k]!);
        hi[k] = Math.max(hi[k]!, pos[3 * i + k]!);
      }
    }
    const mid = lo.map((l, k) => (l + hi[k]!) / 2);
    const half = Math.max(...lo.map((l, k) => (hi[k]! - l) / 2)) || 1;
    for (let i = 0; i < n; i++) {
      for (let k = 0; k < 3; k++) pos[3 * i + k] = (pos[3 * i + k]! - mid[k]!) / half;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    const material = new THREE.LineBasicMaterial({
      color: "#e07a3f",
      transparent: true,
      opacity: 0.75,
    });
    return new THREE.Line(geometry, material);
  }, [system, u]);

  return (
    <div className="attractor">
      <Canvas camera={{ position: [0, 0, 2.6], fov: 50 }}>
        <primitive object={line} />
        <OrbitControls autoRotate autoRotateSpeed={0.8} enablePan={false} />
      </Canvas>
    </div>
  );
}
