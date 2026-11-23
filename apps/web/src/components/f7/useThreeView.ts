"use client";
// Lienzo de three.js con órbita para los visores (D-257): pinta solo cuando algo cambia (no a 60 fps sin motivo) y se
// adapta al tamaño de su contenedor.
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import { addLights } from "./model3d";

export interface ThreeView {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  /** Pide un repintado (se junta con los demás del mismo fotograma). */
  invalidate: () => void;
}

export function useThreeView(): { mountRef: React.RefObject<HTMLDivElement | null>; view: ThreeView | null; failed: boolean } {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [view, setView] = useState<ThreeView | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    } catch {
      setFailed(true);
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.localClippingEnabled = true;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.className = "block h-full w-full touch-none";
    mount.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    addLights(scene);
    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 10000);
    camera.position.set(200, 160, 200);
    const controls = new OrbitControls(camera, renderer.domElement);
    // También con el teclado: el lienzo se puede enfocar y las flechas desplazan la vista (D-260).
    renderer.domElement.tabIndex = 0;
    controls.listenToKeyEvents(renderer.domElement);
    controls.keyPanSpeed = 20;
    controls.enableDamping = true;
    controls.dampingFactor = 0.12;
    let frame = 0;
    const draw = () => {
      frame = 0;
      // Con amortiguación, la órbita sigue moviéndose unos fotogramas después de soltar.
      const moving = controls.update();
      renderer.render(scene, camera);
      if (moving) invalidate();
    };
    const invalidate = () => {
      if (!frame) frame = requestAnimationFrame(draw);
    };
    controls.addEventListener("change", invalidate);
    const resize = () => {
      const { clientWidth: w, clientHeight: h } = mount;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      invalidate();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(mount);
    resize();
    setView({ renderer, scene, camera, controls, invalidate });
    return () => {
      observer.disconnect();
      if (frame) cancelAnimationFrame(frame);
      controls.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
      setView(null);
    };
  }, []);

  return { mountRef, view, failed };
}
