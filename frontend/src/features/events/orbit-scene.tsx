"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";

/** Một hành tinh: màu theo track, kích thước theo số thành viên chính thức. */
export interface OrbitTeam {
  id: string;
  name: string;
  trackLabel: string;
  color: string;
  members: number;
}
import { orbitLayout } from "./orbit-layout";

const SUN = 64;
// Quá nhiều đội thì nhãn chồng nhau; khi đó rê chuột vào hành tinh để xem tên
const LABEL_LIMIT = 60;

interface Planet {
  mesh: THREE.Mesh;
  born: number;
}
interface Stage {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  system: THREE.Group;
  axes: THREE.Group;
  sunLabel: HTMLDivElement;
  rings: { spin: THREE.Group; speed: number }[];
  planets: Planet[];
  ringCount: number;
}

function label(text: string, className: string) {
  const el = document.createElement("div");
  el.className = className;
  el.textContent = text;
  return new CSS2DObject(el);
}

// Bỏ cả nhãn DOM: CSS2DObject chỉ tự gỡ phần tử khi chính nó bị removeFromParent
function clear(group: THREE.Object3D) {
  const labels: CSS2DObject[] = [];
  group.traverse((o) => {
    if (o instanceof CSS2DObject) labels.push(o);
    if (o instanceof THREE.Mesh || o instanceof THREE.Line || o instanceof THREE.Points || o instanceof THREE.Sprite) {
      o.geometry.dispose();
      (o.material as THREE.Material).dispose();
    }
  });
  labels.forEach((l) => l.removeFromParent());
  group.clear();
}

function glowTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  grad.addColorStop(0, "rgba(255,200,120,1)");
  grad.addColorStop(0.25, "rgba(255,107,44,0.55)");
  grad.addColorStop(1, "rgba(255,107,44,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 256, 256);
  return new THREE.CanvasTexture(c);
}

/** Ba trục X (cam), Y (xanh lá), Z (xanh dương) xuyên tâm; nửa âm mờ hơn để thấy chiều. */
function buildAxes(group: THREE.Group, len: number) {
  clear(group);
  const axes: [string, THREE.Vector3, string][] = [
    ["X", new THREE.Vector3(1, 0, 0), "#ff6b2c"],
    ["Y", new THREE.Vector3(0, 1, 0), "#7fe36a"],
    ["Z", new THREE.Vector3(0, 0, 1), "#5cc8ff"],
  ];
  for (const [name, dir, color] of axes) {
    for (const [sign, opacity] of [[1, 0.9], [-1, 0.3]] as const) {
      const geo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), dir.clone().multiplyScalar(len * sign)]);
      group.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color, transparent: true, opacity })));
    }
    const tag = label(name, "rounded-full border-2 border-ink px-2 font-mono text-xs font-extrabold text-ink");
    (tag.element as HTMLElement).style.background = color;
    tag.position.copy(dir.clone().multiplyScalar(len * 1.06));
    group.add(tag);
  }
  // Lưới trên mặt XZ để mắt đọc được độ sâu
  const grid = new THREE.GridHelper(len * 2, 16, 0x3a3a48, 0x23232d);
  (grid.material as THREE.Material).transparent = true;
  (grid.material as THREE.Material).opacity = 0.5;
  group.add(grid);
}

export function OrbitScene({ teams, eventName }: { teams: OrbitTeam[]; eventName: string }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<Stage | null>(null);
  const known = useRef(new Set<string>());
  const [hovered, setHovered] = useState<string | null>(null);

  useEffect(() => {
    const host = hostRef.current!;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch {
      host.className = "grid place-items-center p-6 text-center text-cream";
      host.textContent = "Trình duyệt không hỗ trợ WebGL nên không vẽ được vũ trụ 3D. Xem danh sách đội bên dưới.";
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    host.appendChild(renderer.domElement);
    const css = new CSS2DRenderer();
    css.domElement.className = "pointer-events-none absolute inset-0";
    host.appendChild(css.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#07070c");
    const camera = new THREE.PerspectiveCamera(45, 1, 1, 50000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.enablePan = false;

    scene.add(new THREE.AmbientLight(0xffffff, 0.22));
    // Mặt trời là nguồn sáng: mặt hành tinh quay về tâm sáng, mặt sau tối
    scene.add(new THREE.PointLight(0xfff1d6, 3.2, 0, 0));

    const starPos = new Float32Array(2400 * 3);
    for (let i = 0; i < starPos.length; i += 3) {
      const v = new THREE.Vector3().randomDirection().multiplyScalar(6000 + Math.random() * 6000);
      starPos.set([v.x, v.y, v.z], i);
    }
    const stars = new THREE.Points(
      new THREE.BufferGeometry().setAttribute("position", new THREE.BufferAttribute(starPos, 3)),
      new THREE.PointsMaterial({ color: 0xffffff, size: 1.6, sizeAttenuation: false, transparent: true, opacity: 0.8 }),
    );
    scene.add(stars);

    const sun = new THREE.Mesh(new THREE.SphereGeometry(SUN, 48, 24), new THREE.MeshBasicMaterial({ color: "#ff8a3d" }));
    scene.add(sun);
    const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(), blending: THREE.AdditiveBlending, depthWrite: false }));
    glow.scale.setScalar(SUN * 5.5);
    scene.add(glow);
    const sunTag = label("", "text-center font-black leading-tight text-ink");
    const sunLabel = sunTag.element as HTMLDivElement;
    scene.add(sunTag);

    const axes = new THREE.Group();
    const system = new THREE.Group();
    scene.add(axes, system);
    stageRef.current = { scene, camera, controls, system, axes, sunLabel, rings: [], planets: [], ringCount: -1 };

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = host;
      renderer.setSize(w, h);
      css.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(host);
    resize();

    let paused = false;
    const onEnter = () => (paused = true);
    const onLeave = () => {
      paused = false;
      setHovered(null);
    };
    const ray = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const onMove = (e: PointerEvent) => {
      const r = renderer.domElement.getBoundingClientRect();
      pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(pointer, camera);
      const hit = ray.intersectObjects(stageRef.current?.planets.map((p) => p.mesh) ?? [])[0];
      setHovered((hit?.object.userData.title as string | undefined) ?? null);
    };
    renderer.domElement.addEventListener("pointerenter", onEnter);
    renderer.domElement.addEventListener("pointerleave", onLeave);
    renderer.domElement.addEventListener("pointermove", onMove);

    const still = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let last = performance.now();
    const tick = () => {
      frame = requestAnimationFrame(tick);
      const now = performance.now();
      // Tab ẩn lâu rồi quay lại thì không nhảy cóc cả vòng
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      const s = stageRef.current!;
      if (!paused && !still.matches) {
        // Quay âm quanh trục Y = chiều kim đồng hồ khi nhìn từ trên xuống
        s.rings.forEach((r) => (r.spin.rotation.y -= r.speed * dt));
        s.planets.forEach((p) => (p.mesh.rotation.y += dt * 0.8));
        sun.rotation.y += dt * 0.1;
      }
      s.planets.forEach((p) => {
        const t = Math.min(1, (now - p.born) / 600);
        p.mesh.scale.setScalar(t < 1 ? 1 - Math.pow(1 - t, 3) : 1);
      });
      controls.update();
      renderer.render(scene, camera);
      css.render(scene, camera);
    };
    tick();

    return () => {
      cancelAnimationFrame(frame);
      ro.disconnect();
      controls.dispose();
      clear(scene);
      renderer.dispose();
      renderer.domElement.remove();
      css.domElement.remove();
      stageRef.current = null;
    };
  }, []);

  useEffect(() => {
    const s = stageRef.current;
    if (!s) return;
    clear(s.system);
    const { rings, points } = orbitLayout(teams.length);
    const now = performance.now();
    s.rings = [];
    s.planets = [];
    const spins = rings.map((r, k) => {
      // Mỗi vòng nghiêng một góc khác nhau để quỹ đạo trải ra cả ba chiều
      const pivot = new THREE.Group();
      pivot.rotation.set(0.5 * Math.sin(k * 1.7 + 0.4), 0, 0.38 * Math.cos(k * 2.3));
      const spin = new THREE.Group();
      pivot.add(spin);
      const path = new THREE.BufferGeometry().setFromPoints(new THREE.EllipseCurve(0, 0, r, r).getPoints(128).map((p) => new THREE.Vector3(p.x, 0, p.y)));
      pivot.add(new THREE.LineLoop(path, new THREE.LineBasicMaterial({ color: 0xfff8e0, transparent: true, opacity: 0.28 })));
      s.system.add(pivot);
      // Vòng ngoài quay chậm hơn: một vòng trong mất 60 giây
      s.rings.push({ spin, speed: ((2 * Math.PI) / 60) * (rings[0] / r) });
      return spin;
    });
    points.forEach((p, i) => {
      const t = teams[i];
      const pr = 9 + t.members * 2.5;
      const mesh = new THREE.Mesh(new THREE.SphereGeometry(pr, 32, 16), new THREE.MeshStandardMaterial({ color: t.color, roughness: 0.65, metalness: 0.05 }));
      mesh.position.set(p.x, 0, p.y);
      mesh.userData.title = `${t.name} · ${t.trackLabel} · ${t.members} thành viên`;
      if (teams.length <= LABEL_LIMIT) {
        const tag = label(t.name, "whitespace-nowrap text-[11px] font-bold text-cream [text-shadow:0_1px_2px_#000]");
        tag.position.set(0, -pr - 9, 0);
        mesh.add(tag);
      }
      spins[p.ring].add(mesh);
      // Hành tinh mới mọc dần lên; hành tinh cũ giữ nguyên kích thước khi dựng lại
      s.planets.push({ mesh, born: known.current.has(t.id) ? 0 : now });
      known.current.add(t.id);
    });

    s.sunLabel.innerHTML = "";
    const name = document.createElement("div");
    name.className = "max-w-28 truncate text-xs";
    name.textContent = eventName;
    const num = document.createElement("div");
    num.className = "font-mono text-2xl";
    num.textContent = String(teams.length);
    s.sunLabel.append(name, num);

    // Chỉ đặt lại góc máy khi số vòng đổi, để không giật góc người xem đang xoay
    if (rings.length !== s.ringCount) {
      const reach = (rings.at(-1) ?? SUN * 2) + 80;
      buildAxes(s.axes, reach);
      const dist = reach / Math.tan(THREE.MathUtils.degToRad(s.camera.fov / 2)) * 0.95;
      s.camera.position.set(dist * 0.55, dist * 0.5, dist * 0.7);
      s.controls.maxDistance = dist * 2.5;
      s.controls.minDistance = SUN * 2;
      s.ringCount = rings.length;
    }
  }, [teams, eventName]);

  return (
    <div className="relative">
      <div ref={hostRef} role="img" aria-label={`${eventName}: ${teams.length} đội thi xoay quanh cuộc thi trong không gian 3D`} className="relative aspect-[4/3] w-full cursor-grab overflow-hidden active:cursor-grabbing sm:aspect-[16/10]" />
      {hovered && (
        <p role="status" className="chip pointer-events-none absolute left-3 top-3 bg-paper text-sm">
          {hovered}
        </p>
      )}
    </div>
  );
}
