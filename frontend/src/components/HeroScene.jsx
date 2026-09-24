// The 3D bit on the sign-in page: a glassy "sage crystal" with a wireframe
// shell, two orbit rings and a drifting particle field. It's lazy-loaded so
// three.js never lands in the main bundle, pauses when the tab is hidden,
// holds still for reduced motion, and frees every GPU buffer on unmount.
import { useEffect, useRef } from "react";
import * as THREE from "three";

export default function HeroScene() {
  const host = useRef(null);

  useEffect(() => {
    const el = host.current;
    if (!el) return undefined;

    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
    } catch {
      el.dataset.nowebgl = "1"; // CSS fallback orb shows instead
      return undefined;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(0, 0, 7.5);

    // lights: teal key, a violet rim (the only violet on screen besides the logo), soft fill
    scene.add(new THREE.AmbientLight(0x8fb3c9, 0.5));
    const key = new THREE.PointLight(0x5eead4, 40, 30);
    key.position.set(4, 3, 5);
    const rim = new THREE.PointLight(0xa78bfa, 45, 30);
    rim.position.set(-5, -2, 2);
    scene.add(key, rim);

    const group = new THREE.Group();
    scene.add(group);

    // crystal core
    const coreGeo = new THREE.IcosahedronGeometry(1.35, 0);
    const coreMat = new THREE.MeshPhysicalMaterial({
      color: 0x3cbfa8, metalness: 0.15, roughness: 0.12, clearcoat: 1, clearcoatRoughness: 0.08,
      iridescence: 0.9, iridescenceIOR: 1.4, flatShading: true, emissive: 0x0b3b36, emissiveIntensity: 0.6,
    });
    const core = new THREE.Mesh(coreGeo, coreMat);
    group.add(core);

    // wireframe shell a size up
    const shellGeo = new THREE.IcosahedronGeometry(1.95, 1);
    const shellMat = new THREE.MeshBasicMaterial({ color: 0x7fe2d0, wireframe: true, transparent: true, opacity: 0.16 });
    const shell = new THREE.Mesh(shellGeo, shellMat);
    group.add(shell);

    // orbit rings
    const ringGeo = new THREE.TorusGeometry(2.6, 0.012, 8, 180);
    const ringMatA = new THREE.MeshBasicMaterial({ color: 0x5eead4, transparent: true, opacity: 0.55 });
    const ringMatB = new THREE.MeshBasicMaterial({ color: 0x7cc4f0, transparent: true, opacity: 0.4 });
    const ringA = new THREE.Mesh(ringGeo, ringMatA);
    const ringB = new THREE.Mesh(ringGeo, ringMatB);
    ringA.rotation.set(1.2, 0.2, 0);
    ringB.rotation.set(-0.9, 0.7, 0.4);
    ringB.scale.setScalar(1.12);
    group.add(ringA, ringB);

    // particle field
    const count = 600;
    const positions = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const r = 3 + Math.random() * 4.5;
      const t = Math.random() * Math.PI * 2;
      const p = Math.acos(2 * Math.random() - 1);
      positions[i * 3] = r * Math.sin(p) * Math.cos(t);
      positions[i * 3 + 1] = r * Math.sin(p) * Math.sin(t) * 0.6;
      positions[i * 3 + 2] = r * Math.cos(p);
    }
    const dotsGeo = new THREE.BufferGeometry();
    dotsGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const dotsMat = new THREE.PointsMaterial({ color: 0x99f6e4, size: 0.035, transparent: true, opacity: 0.8, depthWrite: false });
    const dots = new THREE.Points(dotsGeo, dotsMat);
    scene.add(dots);

    // sizing
    const resize = () => {
      const { clientWidth: w, clientHeight: h } = el;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();

    // input + motion preference, both kept live
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let still = motion.matches;
    const onMotion = (e) => { still = e.matches; };
    motion.addEventListener("change", onMotion);
    const target = { x: 0, y: 0 };
    const onPointer = (e) => {
      target.x = (e.clientX / window.innerWidth - 0.5) * 0.6;
      target.y = (e.clientY / window.innerHeight - 0.5) * 0.4;
    };
    window.addEventListener("pointermove", onPointer, { passive: true });

    let raf = 0;
    let last = performance.now();
    let t = 0;
    const tick = (now = performance.now()) => {
      raf = requestAnimationFrame(tick);
      const dt = Math.min((now - last) / 1000, 0.05); // clamp so a background tab doesn't jump
      last = now;
      if (document.hidden) return;
      t += dt;
      if (!still) {
        core.rotation.y += dt * 0.35;
        core.rotation.x += dt * 0.12;
        shell.rotation.y -= dt * 0.12;
        ringA.rotation.z += dt * 0.25;
        ringB.rotation.z -= dt * 0.18;
        dots.rotation.y += dt * 0.03;
        group.position.y = Math.sin(t * 0.9) * 0.08;
      }
      group.rotation.y += (target.x - group.rotation.y) * 0.05;
      group.rotation.x += (target.y - group.rotation.x) * 0.05;
      renderer.render(scene, camera);
    };
    tick();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      motion.removeEventListener("change", onMotion);
      window.removeEventListener("pointermove", onPointer);
      for (const g of [coreGeo, shellGeo, ringGeo, dotsGeo]) g.dispose();
      for (const m of [coreMat, shellMat, ringMatA, ringMatB, dotsMat]) m.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  return <div ref={host} className="hero-canvas" style={{ position: "absolute", inset: 0 }} aria-hidden="true" />;
}
