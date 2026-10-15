import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';

interface Cinematic3DBackgroundProps {
  className?: string;
}

interface AgentTokenConfig {
  id: string;
  name: string;
  provider: string;
  x: number;
  y: number;
  z: number;
  radius: number;
  floatSpeed: number;
  floatAmp: number;
  phase: number;
}

// Deliberate placement: Harmoniously orbiting the 3D optical control plane array on the right flank
// Leaves the entire left half (x: < 30) completely dedicated to crisp, unencumbered typography
const AGENT_TOKENS: AgentTokenConfig[] = [
  {
    id: 'claude',
    name: 'Claude Code',
    provider: 'Anthropic',
    x: 120,
    y: 165,
    z: 25,
    radius: 29,
    floatSpeed: 0.74,
    floatAmp: 11,
    phase: 0.3
  },
  {
    id: 'cursor',
    name: 'Cursor',
    provider: 'Anysphere',
    x: 255,
    y: 115,
    z: 45,
    radius: 31,
    floatSpeed: 0.84,
    floatAmp: 13,
    phase: 1.6
  },
  {
    id: 'codex',
    name: 'OpenAI Codex',
    provider: 'OpenAI',
    x: 325,
    y: 15,
    z: -10,
    radius: 28,
    floatSpeed: 0.7,
    floatAmp: 11,
    phase: 3.1
  },
  {
    id: 'copilot',
    name: 'GitHub Copilot',
    provider: 'Microsoft',
    x: 275,
    y: -80,
    z: 40,
    radius: 27,
    floatSpeed: 0.78,
    floatAmp: 12,
    phase: 2.2
  },
  {
    id: 'windsurf',
    name: 'Windsurf',
    provider: 'Codeium',
    x: 165,
    y: -140,
    z: -20,
    radius: 26,
    floatSpeed: 0.72,
    floatAmp: 10,
    phase: 4.8
  },
  {
    id: 'devin',
    name: 'Devin',
    provider: 'Cognition',
    x: 65,
    y: -155,
    z: 30,
    radius: 28,
    floatSpeed: 0.68,
    floatAmp: 12,
    phase: 5.6
  }
];

// Helper to draw authentic agent vector logos onto high-resolution 512x512 canvas textures
function createAgentDiscTexture(agent: AgentTokenConfig): THREE.CanvasTexture {
  const size = 512;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');

  if (!ctx) {
    return new THREE.CanvasTexture(canvas);
  }

  const cx = size / 2;
  const cy = size / 2;
  const r = size * 0.44;

  // 1. Base Circular Glass Disc Mask
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.clip();

  // Glass disc radial gradient: Deep Midnight #0F1F3D to Navy #060B16
  const bgGrad = ctx.createRadialGradient(cx, cy - 30, 20, cx, cy, r);
  bgGrad.addColorStop(0, '#152747');
  bgGrad.addColorStop(0.55, '#0E1A33');
  bgGrad.addColorStop(1, '#070E1C');
  ctx.fillStyle = bgGrad;
  ctx.fillRect(0, 0, size, size);

  // Subtle interior concentric telemetry ring
  ctx.strokeStyle = 'rgba(128, 181, 255, 0.25)';
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.arc(cx, cy, r * 0.75, 0, Math.PI * 2);
  ctx.stroke();

  // Luminous radial back-glow for vector logo
  const glowGrad = ctx.createRadialGradient(cx, cy - 24, 0, cx, cy - 24, 95);
  glowGrad.addColorStop(0, 'rgba(76, 141, 255, 0.4)');
  glowGrad.addColorStop(1, 'rgba(52, 120, 246, 0)');
  ctx.fillStyle = glowGrad;
  ctx.beginPath();
  ctx.arc(cx, cy - 24, 95, 0, Math.PI * 2);
  ctx.fill();

  // 2. Render Authentic Vector Logo (Centered above label)
  const iconY = cy - 24;
  const iconScale = 4.0;
  ctx.save();
  ctx.translate(cx, iconY);
  ctx.scale(iconScale, iconScale);

  if (agent.id === 'claude') {
    // Anthropic Spark / Asterisk Mark
    ctx.translate(-20, -16);
    ctx.fillStyle = '#F59E0B';
    ctx.beginPath();
    ctx.moveTo(23.1, 7.2);
    ctx.lineTo(20, 12.8);
    ctx.lineTo(16.9, 7.2);
    ctx.bezierCurveTo(16.4, 6.3, 15.3, 5.9, 14.4, 6.4);
    ctx.bezierCurveTo(13.5, 6.9, 13.1, 8.0, 13.6, 8.9);
    ctx.lineTo(16.8, 14.6);
    ctx.lineTo(10.4, 14.6);
    ctx.bezierCurveTo(9.4, 14.6, 8.5, 15.5, 8.5, 16.5);
    ctx.bezierCurveTo(8.5, 17.5, 9.4, 18.4, 10.4, 18.4);
    ctx.lineTo(16.8, 18.4);
    ctx.lineTo(13.6, 24.1);
    ctx.bezierCurveTo(13.1, 25.0, 13.5, 26.1, 14.4, 26.6);
    ctx.bezierCurveTo(15.3, 27.1, 16.4, 26.7, 16.9, 25.8);
    ctx.lineTo(20, 20.2);
    ctx.lineTo(23.1, 25.8);
    ctx.bezierCurveTo(23.6, 26.7, 24.7, 27.1, 25.6, 26.6);
    ctx.bezierCurveTo(26.5, 26.1, 26.9, 25.0, 26.4, 24.1);
    ctx.lineTo(23.2, 18.4);
    ctx.lineTo(29.6, 18.4);
    ctx.bezierCurveTo(30.6, 18.4, 31.5, 17.5, 31.5, 16.5);
    ctx.bezierCurveTo(31.5, 15.5, 30.6, 14.6, 29.6, 14.6);
    ctx.lineTo(23.2, 14.6);
    ctx.lineTo(26.4, 8.9);
    ctx.bezierCurveTo(26.9, 8.0, 26.5, 6.9, 25.6, 6.4);
    ctx.bezierCurveTo(24.7, 5.9, 23.6, 6.3, 23.1, 7.2);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = '#FEF3C7';
    ctx.beginPath();
    ctx.arc(20, 16.5, 3.2, 0, Math.PI * 2);
    ctx.fill();
  } else if (agent.id === 'cursor') {
    // Cursor 3D Isometric Rose Cube
    ctx.translate(-16, -17);
    // Top facet
    ctx.fillStyle = '#FB7185';
    ctx.strokeStyle = '#FFE4E6';
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(16, 2);
    ctx.lineTo(30, 10);
    ctx.lineTo(16, 18);
    ctx.lineTo(2, 10);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    // Left facet
    ctx.fillStyle = '#E11D48';
    ctx.beginPath();
    ctx.moveTo(2, 10);
    ctx.lineTo(16, 18);
    ctx.lineTo(16, 32);
    ctx.lineTo(2, 24);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    // Right facet
    ctx.fillStyle = '#BE123C';
    ctx.beginPath();
    ctx.moveTo(16, 18);
    ctx.lineTo(30, 10);
    ctx.lineTo(30, 24);
    ctx.lineTo(16, 32);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    // Center glow point
    ctx.fillStyle = '#FFFFFF';
    ctx.beginPath();
    ctx.arc(16, 18, 2.6, 0, Math.PI * 2);
    ctx.fill();
  } else if (agent.id === 'codex') {
    // OpenAI Spiral Knot (Bright Emerald / Mint)
    ctx.translate(-20, -20);
    ctx.strokeStyle = '#34D399';
    ctx.lineWidth = 2.4;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(28.5, 17.3); ctx.lineTo(28.5, 12.7); ctx.arcTo(28.5, 10, 25.8, 10, 2.7); ctx.lineTo(21.2, 10);
    ctx.moveTo(12.7, 28.5); ctx.lineTo(17.3, 28.5); ctx.arcTo(20, 28.5, 20, 25.8, 2.7); ctx.lineTo(20, 21.2);
    ctx.moveTo(22.7, 28.5); ctx.lineTo(27.3, 28.5); ctx.arcTo(30, 28.5, 30, 25.8, 2.7); ctx.lineTo(30, 21.2);
    ctx.moveTo(11.5, 22.7); ctx.lineTo(11.5, 18.1); ctx.arcTo(11.5, 15.4, 14.2, 15.4, 2.7); ctx.lineTo(18.8, 15.4);
    ctx.moveTo(17.3, 11.5); ctx.lineTo(12.7, 11.5); ctx.arcTo(10, 11.5, 10, 14.2, 2.7); ctx.lineTo(10, 18.8);
    ctx.moveTo(27.3, 11.5); ctx.lineTo(20, 7.3); ctx.lineTo(12.7, 11.5);
    ctx.moveTo(27.3, 28.5); ctx.lineTo(20, 32.7); ctx.lineTo(12.7, 28.5);
    ctx.moveTo(10, 14.2); ctx.lineTo(20, 20); ctx.lineTo(30, 14.2);
    ctx.moveTo(10, 25.8); ctx.lineTo(20, 20); ctx.lineTo(30, 25.8);
    ctx.stroke();
    ctx.fillStyle = '#6EE7B7';
    ctx.beginPath();
    ctx.arc(20, 20, 3.4, 0, Math.PI * 2);
    ctx.fill();
  } else if (agent.id === 'devin') {
    // Devin Code Box
    ctx.translate(-20, -20);
    ctx.fillStyle = '#18181B';
    ctx.strokeStyle = '#22D3EE';
    ctx.lineWidth = 2.4;
    ctx.beginPath();
    ctx.roundRect(7, 7, 26, 26, 6);
    ctx.fill();
    ctx.stroke();
    ctx.strokeStyle = '#67E8F9';
    ctx.lineWidth = 2.6;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(15, 15); ctx.lineTo(11, 20); ctx.lineTo(15, 25);
    ctx.moveTo(25, 15); ctx.lineTo(29, 20); ctx.lineTo(25, 25);
    ctx.stroke();
    ctx.strokeStyle = '#38BDF8';
    ctx.lineWidth = 2.2;
    ctx.beginPath();
    ctx.moveTo(22, 13); ctx.lineTo(18, 27);
    ctx.stroke();
  } else if (agent.id === 'copilot') {
    // GitHub Copilot Visor / Bot Mark
    ctx.translate(-20, -20);
    ctx.fillStyle = '#172541';
    ctx.strokeStyle = '#38BDF8';
    ctx.lineWidth = 2.4;
    ctx.beginPath();
    ctx.roundRect(8, 10, 24, 20, 8);
    ctx.fill();
    ctx.stroke();
    // Eyes
    ctx.fillStyle = '#80B5FF';
    ctx.beginPath();
    ctx.arc(15, 20, 3.0, 0, Math.PI * 2);
    ctx.arc(25, 20, 3.0, 0, Math.PI * 2);
    ctx.fill();
    // Antenna
    ctx.strokeStyle = '#80B5FF';
    ctx.lineWidth = 2.2;
    ctx.beginPath();
    ctx.moveTo(20, 10); ctx.lineTo(20, 5);
    ctx.stroke();
    ctx.fillStyle = '#80B5FF';
    ctx.beginPath();
    ctx.arc(20, 4.5, 2.5, 0, Math.PI * 2);
    ctx.fill();
  } else {
    // Windsurf Wave Mark
    ctx.translate(-20, -20);
    const grad = ctx.createLinearGradient(8, 8, 32, 32);
    grad.addColorStop(0, '#22D3EE');
    grad.addColorStop(1, '#3B82F6');
    ctx.strokeStyle = grad;
    ctx.lineWidth = 3.6;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(8, 20);
    ctx.bezierCurveTo(12, 12, 18, 12, 22, 20);
    ctx.bezierCurveTo(26, 28, 32, 28, 36, 20);
    ctx.moveTo(11, 26);
    ctx.bezierCurveTo(15, 20, 19, 20, 23, 26);
    ctx.bezierCurveTo(27, 32, 31, 32, 34, 26);
    ctx.stroke();
  }
  ctx.restore();

  // 3. Crisp Enterprise Typography on Disc
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  // Agent Name
  ctx.font = '700 24px -apple-system, BlinkMacSystemFont, "Inter", sans-serif';
  ctx.fillStyle = '#F5F8FF';
  ctx.fillText(agent.name.toUpperCase(), cx, cy + 94);

  // Provider Tag
  ctx.font = '600 16px -apple-system, BlinkMacSystemFont, "Inter", sans-serif';
  ctx.fillStyle = '#80B5FF';
  ctx.fillText(agent.provider, cx, cy + 124);

  ctx.restore();

  // 4. Outer Beveled Metallic Rim Border
  const rimGrad = ctx.createLinearGradient(0, cy - r, 0, cy + r);
  rimGrad.addColorStop(0, 'rgba(128, 181, 255, 0.98)');
  rimGrad.addColorStop(0.5, 'rgba(52, 120, 246, 0.65)');
  rimGrad.addColorStop(1, 'rgba(29, 59, 112, 0.95)');

  ctx.strokeStyle = rimGrad;
  ctx.lineWidth = 9;
  ctx.beginPath();
  ctx.arc(cx, cy, r - 3, 0, Math.PI * 2);
  ctx.stroke();

  // Glint
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
  ctx.lineWidth = 3.5;
  ctx.beginPath();
  ctx.arc(cx, cy, r - 3, -Math.PI * 0.75, -Math.PI * 0.25);
  ctx.stroke();

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

export const Cinematic3DBackground: React.FC<Cinematic3DBackgroundProps> = ({ className = '' }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [webGLSupported, setWebGLSupported] = useState<boolean>(() => {
    try {
      const canvasTest = document.createElement('canvas');
      return !!(canvasTest.getContext('webgl') || canvasTest.getContext('experimental-webgl'));
    } catch {
      return false;
    }
  });

  useEffect(() => {
    if (!webGLSupported) return;

    const container = containerRef.current;
    if (!container) return;

    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    let prefersReducedMotion = motionQuery.matches;
    const handleMotionChange = (e: MediaQueryListEvent) => {
      prefersReducedMotion = e.matches;
    };
    motionQuery.addEventListener('change', handleMotionChange);

    // 1. SCENE & ATMOSPHERIC FOG (Strict Brand Palette: Midnight Navy #080D1B)
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x080D1B);
    scene.fog = new THREE.FogExp2(0x080D1B, 0.0015);

    // 2. CAMERA SETUP
    let width = container.clientWidth || window.innerWidth;
    let height = container.clientHeight || window.innerHeight;
    const camera = new THREE.PerspectiveCamera(45, width / height, 1, 3500);
    camera.position.set(0, 0, 480);

    // 3. RENDERER SETUP
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: false,
        powerPreference: 'high-performance'
      });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(width, height);
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.28;
      container.appendChild(renderer.domElement);
    } catch {
      setWebGLSupported(false);
      return;
    }

    // 4. LIGHTING SYSTEM (Volumetric Blue Hierarchy)
    const ambientLight = new THREE.AmbientLight(0x111D35, 2.6);
    scene.add(ambientLight);

    const keyLight = new THREE.DirectionalLight(0x3478F6, 4.2);
    keyLight.position.set(240, 260, 320);
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0x1D3B70, 2.2);
    fillLight.position.set(-280, -160, 220);
    scene.add(fillLight);

    const corePointLight = new THREE.PointLight(0x4C8DFF, 4.0, 980, 1.3);
    corePointLight.position.set(40, 20, 60);
    scene.add(corePointLight);

    const rimPointLight = new THREE.PointLight(0x80B5FF, 3.4, 880, 1.4);
    rimPointLight.position.set(210, 80, 190);
    scene.add(rimPointLight);

    const masterGroup = new THREE.Group();
    scene.add(masterGroup);

    // 5. VOLUMETRIC LIGHT BLOOM SPRITE (Behind optical lens cluster on right flank)
    const createBloomTexture = () => {
      const cv = document.createElement('canvas');
      cv.width = 256;
      cv.height = 256;
      const cx = cv.getContext('2d');
      if (cx) {
        const g = cx.createRadialGradient(128, 128, 0, 128, 128, 128);
        g.addColorStop(0, 'rgba(76, 141, 255, 0.45)');
        g.addColorStop(0.35, 'rgba(52, 120, 246, 0.25)');
        g.addColorStop(0.7, 'rgba(29, 59, 112, 0.1)');
        g.addColorStop(1, 'rgba(8, 13, 27, 0)');
        cx.fillStyle = g;
        cx.fillRect(0, 0, 256, 256);
      }
      return new THREE.CanvasTexture(cv);
    };

    const bloomTex = createBloomTexture();
    const bloomMat = new THREE.SpriteMaterial({
      map: bloomTex,
      transparent: true,
      blending: THREE.AdditiveBlending,
      opacity: 0.88
    });
    const bloomSprite = new THREE.Sprite(bloomMat);
    bloomSprite.position.set(220, 20, -50);
    bloomSprite.scale.set(420, 420, 1);
    masterGroup.add(bloomSprite);



    // 7. SCULPTURAL OPTICAL LENS RINGS (Concentric Glass Array, Optilayer Image 3)
    const lensRingGroup = new THREE.Group();
    lensRingGroup.position.set(210, 20, -20);
    lensRingGroup.rotation.set(0.34, -0.44, 0.16);
    masterGroup.add(lensRingGroup);

    const lensConfigs = [
      { radius: 145, tube: 2.4, color: 0x3478F6, opacity: 0.65, zOffset: 0 },
      { radius: 115, tube: 2.0, color: 0x80B5FF, opacity: 0.55, zOffset: -32 },
      { radius: 175, tube: 1.8, color: 0x1D3B70, opacity: 0.45, zOffset: 38 },
      { radius: 82, tube: 2.2, color: 0x4C8DFF, opacity: 0.75, zOffset: -60 }
    ];

    const lensMeshes: THREE.Mesh[] = [];
    lensConfigs.forEach(cfg => {
      const geo = new THREE.TorusGeometry(cfg.radius, cfg.tube, 16, 120);
      const mat = new THREE.MeshStandardMaterial({
        color: cfg.color,
        roughness: 0.1,
        metalness: 0.92,
        transparent: true,
        opacity: cfg.opacity
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.z = cfg.zOffset;
      lensRingGroup.add(mesh);
      lensMeshes.push(mesh);
    });

    // 8. FLOATING CRYSTALLINE CUBES (Glowing Chamfered Prisms, Image 2)
    interface CrystallineNode {
      group: THREE.Group;
      baseX: number;
      baseY: number;
      baseZ: number;
      rotX: number;
      rotY: number;
      bobSpeed: number;
      bobAmp: number;
      phase: number;
    }

    const crystallineNodes: CrystallineNode[] = [];
    const cubeConfigs = [
      { size: 32, x: 205, y: -50, z: 45, rotX: 0.005, rotY: 0.007, bob: 0.8, amp: 14, phase: 0 },
      { size: 24, x: -190, y: -65, z: 15, rotX: -0.006, rotY: 0.005, bob: 0.7, amp: 12, phase: 1.5 },
      { size: 36, x: 310, y: 60, z: -35, rotX: 0.004, rotY: -0.005, bob: 0.6, amp: 16, phase: 2.8 },
      { size: 22, x: -140, y: 110, z: -60, rotX: 0.007, rotY: 0.006, bob: 0.9, amp: 10, phase: 4.1 },
      { size: 24, x: 70, y: -110, z: 25, rotX: -0.005, rotY: 0.008, bob: 0.75, amp: 11, phase: 5.3 }
    ];

    cubeConfigs.forEach(cfg => {
      const cubeGroup = new THREE.Group();

      const cubeGeo = new THREE.BoxGeometry(cfg.size, cfg.size, cfg.size);
      const glassMat = new THREE.MeshStandardMaterial({
        color: 0x1D3B70,
        emissive: 0x0E2045,
        roughness: 0.08,
        metalness: 0.9,
        transparent: true,
        opacity: 0.72
      });
      const glassMesh = new THREE.Mesh(cubeGeo, glassMat);
      cubeGroup.add(glassMesh);

      const wireGeo = new THREE.BoxGeometry(cfg.size * 0.97, cfg.size * 0.97, cfg.size * 0.97);
      const wireMat = new THREE.MeshBasicMaterial({
        color: 0x80B5FF,
        wireframe: true,
        transparent: true,
        opacity: 0.7
      });
      const wireMesh = new THREE.Mesh(wireGeo, wireMat);
      cubeGroup.add(wireMesh);

      const coreGeo = new THREE.SphereGeometry(cfg.size * 0.22, 12, 12);
      const coreMat = new THREE.MeshBasicMaterial({
        color: 0xC6DCFF
      });
      const coreMesh = new THREE.Mesh(coreGeo, coreMat);
      cubeGroup.add(coreMesh);

      cubeGroup.position.set(cfg.x, cfg.y, cfg.z);
      masterGroup.add(cubeGroup);

      crystallineNodes.push({
        group: cubeGroup,
        baseX: cfg.x,
        baseY: cfg.y,
        baseZ: cfg.z,
        rotX: cfg.rotX,
        rotY: cfg.rotY,
        bobSpeed: cfg.bob,
        bobAmp: cfg.amp,
        phase: cfg.phase
      });
    });

    // 9. FLOATING CIRCULAR AI AGENT ELEMENTS (Genuinely Supported AI Agents in 3D Space)
    interface AgentTokenMeshNode {
      group: THREE.Group;
      cfg: AgentTokenConfig;
      rimMesh: THREE.Mesh;
      discMesh: THREE.Mesh;
      baseX: number;
      baseY: number;
      baseZ: number;
    }

    const agentMeshNodes: AgentTokenMeshNode[] = [];
    const texturesToDispose: THREE.CanvasTexture[] = [];

    AGENT_TOKENS.forEach(cfg => {
      const tokenGroup = new THREE.Group();
      const texture = createAgentDiscTexture(cfg);
      texturesToDispose.push(texture);

      const discGeo = new THREE.CircleGeometry(cfg.radius, 48);
      const discMat = new THREE.MeshBasicMaterial({
        map: texture,
        transparent: true,
        side: THREE.DoubleSide
      });
      const discMesh = new THREE.Mesh(discGeo, discMat);
      tokenGroup.add(discMesh);

      const rimGeo = new THREE.TorusGeometry(cfg.radius, 1.6, 16, 48);
      const rimMat = new THREE.MeshStandardMaterial({
        color: 0x80B5FF,
        roughness: 0.15,
        metalness: 0.94,
        transparent: true,
        opacity: 0.9
      });
      const rimMesh = new THREE.Mesh(rimGeo, rimMat);
      tokenGroup.add(rimMesh);

      tokenGroup.position.set(cfg.x, cfg.y, cfg.z);
      masterGroup.add(tokenGroup);

      agentMeshNodes.push({
        group: tokenGroup,
        cfg,
        rimMesh,
        discMesh,
        baseX: cfg.x,
        baseY: cfg.y,
        baseZ: cfg.z
      });
    });

    // 10. DRIFTING PARTICULATE EMBERS (480 Luminescent Data Particles in Ice & Electric Blue)
    const particleCount = 480;
    const particlePositions = new Float32Array(particleCount * 3);
    const particleColors = new Float32Array(particleCount * 3);

    const blueColors = [
      new THREE.Color(0x80B5FF),
      new THREE.Color(0x4C8DFF),
      new THREE.Color(0x3478F6),
      new THREE.Color(0xC6DCFF),
      new THREE.Color(0x1D3B70)
    ];

    for (let i = 0; i < particleCount; i++) {
      const radius = 60 + Math.random() * 520;
      const angle = Math.random() * Math.PI * 2;
      const h = (Math.random() - 0.5) * 560;
      const d = (Math.random() - 0.5) * 400;

      particlePositions[i * 3] = Math.cos(angle) * radius;
      particlePositions[i * 3 + 1] = h;
      particlePositions[i * 3 + 2] = Math.sin(angle) * radius * 0.45 + d;

      const col = blueColors[Math.floor(Math.random() * blueColors.length)];
      particleColors[i * 3] = col.r;
      particleColors[i * 3 + 1] = col.g;
      particleColors[i * 3 + 2] = col.b;
    }

    const particlesGeo = new THREE.BufferGeometry();
    particlesGeo.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));
    particlesGeo.setAttribute('color', new THREE.BufferAttribute(particleColors, 3));

    const createMoteTexture = () => {
      const cv = document.createElement('canvas');
      cv.width = 64;
      cv.height = 64;
      const cx = cv.getContext('2d');
      if (cx) {
        const grad = cx.createRadialGradient(32, 32, 0, 32, 32, 32);
        grad.addColorStop(0, 'rgba(255, 255, 255, 1)');
        grad.addColorStop(0.25, 'rgba(128, 181, 255, 0.92)');
        grad.addColorStop(0.65, 'rgba(52, 120, 246, 0.3)');
        grad.addColorStop(1, 'rgba(8, 13, 27, 0)');
        cx.fillStyle = grad;
        cx.fillRect(0, 0, 64, 64);
      }
      return new THREE.CanvasTexture(cv);
    };

    const moteTexture = createMoteTexture();
    const particlesMat = new THREE.PointsMaterial({
      size: 4.8,
      map: moteTexture,
      transparent: true,
      vertexColors: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      opacity: 0.74
    });

    const particleSystem = new THREE.Points(particlesGeo, particlesMat);
    scene.add(particleSystem);

    // 11. POINTER & SCROLL PARALLAX
    const mouse = { x: 0, y: 0, targetX: 0, targetY: 0 };
    let scrollY = 0;
    let targetScrollY = 0;

    const handleMouseMove = (e: MouseEvent) => {
      mouse.targetX = (e.clientX / window.innerWidth - 0.5) * 2;
      mouse.targetY = (e.clientY / window.innerHeight - 0.5) * 2;
    };

    const handleScroll = () => {
      const maxScroll = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
      targetScrollY = Math.min(Math.max(window.scrollY / maxScroll, 0), 1);
    };

    window.addEventListener('mousemove', handleMouseMove, { passive: true });
    window.addEventListener('scroll', handleScroll, { passive: true });

    const handleResize = () => {
      if (!container) return;
      width = container.clientWidth || window.innerWidth;
      height = container.clientHeight || window.innerHeight;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };
    window.addEventListener('resize', handleResize);

    let isVisible = true;
    const observer = new IntersectionObserver(([entry]) => {
      isVisible = entry.isIntersecting;
    });
    observer.observe(container);

    // 12. CONTINUOUS LIVING ANIMATION LOOP
    let animationFrameId: number;
    const clock = new THREE.Clock();

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      if (!isVisible) return;

      const elapsedTime = clock.getElapsedTime();
      const motionFactor = prefersReducedMotion ? 0.08 : 1.0;

      mouse.x += (mouse.targetX - mouse.x) * 0.045;
      mouse.y += (mouse.targetY - mouse.y) * 0.045;
      scrollY += (targetScrollY - scrollY) * 0.06;

      const idleDriftX = Math.sin(elapsedTime * 0.32) * 20;
      const idleDriftY = Math.cos(elapsedTime * 0.24) * 14;

      const targetCamX = mouse.x * 38 + idleDriftX * motionFactor;
      const targetCamY = -mouse.y * 22 + idleDriftY * motionFactor - scrollY * 75;
      const targetCamZ = 480 + scrollY * 110;

      camera.position.x += (targetCamX - camera.position.x) * 0.04;
      camera.position.y += (targetCamY - camera.position.y) * 0.04;
      camera.position.z += (targetCamZ - camera.position.z) * 0.04;
      camera.lookAt(20, -scrollY * 35, 0);

      corePointLight.intensity = 3.4 + Math.sin(elapsedTime * 1.6) * 0.9 * motionFactor;
      rimPointLight.position.x = 210 + mouse.x * 120 + Math.sin(elapsedTime * 0.6) * 45;
      rimPointLight.position.y = 80 - mouse.y * 80 + Math.cos(elapsedTime * 0.5) * 35;



      // B. Animate Concentric Optical Lens Array (Image 3 Optilayer)
      lensRingGroup.rotation.z += 0.0018 * motionFactor;
      lensRingGroup.rotation.y = -0.44 + mouse.x * 0.08 + Math.sin(elapsedTime * 0.28) * 0.05;
      lensMeshes.forEach((mesh, idx) => {
        mesh.rotation.x += (idx % 2 === 0 ? 0.001 : -0.0012) * motionFactor;
      });

      // C. Animate Crystalline Cubes (Image 2 Glass Prisms)
      crystallineNodes.forEach(node => {
        node.group.rotation.x += node.rotX * motionFactor;
        node.group.rotation.y += node.rotY * motionFactor;

        const bob = Math.sin(elapsedTime * node.bobSpeed + node.phase) * node.bobAmp;
        node.group.position.y = node.baseY + bob * motionFactor;
        node.group.position.x = node.baseX + mouse.x * 14;
      });

      // D. Animate Floating AI Agent Discs
      agentMeshNodes.forEach(node => {
        const bob = Math.sin(elapsedTime * node.cfg.floatSpeed + node.cfg.phase) * node.cfg.floatAmp;
        node.group.position.y = node.baseY + bob * motionFactor;
        node.group.position.x = node.baseX + mouse.x * 18;
        node.group.position.z = node.baseZ + mouse.y * 12;

        node.group.rotation.y = mouse.x * 0.1 + Math.sin(elapsedTime * 0.5 + node.cfg.phase) * 0.06;
        node.group.rotation.x = -mouse.y * 0.08 + Math.cos(elapsedTime * 0.4 + node.cfg.phase) * 0.05;
      });

      // E. Particulate Drift
      particleSystem.rotation.y += 0.00045 * motionFactor;
      particleSystem.rotation.x = mouse.y * 0.04;

      renderer.render(scene, camera);
    };

    animate();

    // 13. CLEANUP HANDLER
    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('scroll', handleScroll);
      window.removeEventListener('resize', handleResize);
      motionQuery.removeEventListener('change', handleMotionChange);
      observer.disconnect();


      particlesGeo.dispose();
      particlesMat.dispose();
      moteTexture.dispose();
      bloomTex.dispose();
      bloomMat.dispose();

      lensConfigs.forEach(() => {
        lensMeshes.forEach(m => {
          m.geometry.dispose();
          (m.material as THREE.Material).dispose();
        });
      });

      crystallineNodes.forEach(n => {
        n.group.children.forEach(c => {
          if (c instanceof THREE.Mesh) {
            c.geometry.dispose();
            (c.material as THREE.Material).dispose();
          }
        });
      });

      agentMeshNodes.forEach(n => {
        n.rimMesh.geometry.dispose();
        (n.rimMesh.material as THREE.Material).dispose();
        n.discMesh.geometry.dispose();
        (n.discMesh.material as THREE.Material).dispose();
      });

      texturesToDispose.forEach(t => t.dispose());

      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
      renderer.dispose();
    };
  }, [webGLSupported]);

  return (
    <div
      ref={containerRef}
      className={`as-cinematic-3d-bg ${className}`}
      aria-hidden="true"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 0,
        pointerEvents: 'none',
        overflow: 'hidden',
        background: '#080D1B'
      }}
    >
      {!webGLSupported && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: `
              radial-gradient(ellipse 70% 50% at 50% -15%, rgba(52, 120, 246, 0.25), transparent 70%),
              radial-gradient(ellipse 60% 40% at 85% 55%, rgba(29, 59, 112, 0.35), transparent 60%),
              radial-gradient(ellipse 60% 40% at 15% 65%, rgba(76, 141, 255, 0.18), transparent 60%),
              #080D1B
            `
          }}
        />
      )}

      {/* Atmospheric Scrim to Ensure 100% Foreground Typography Legibility */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: 'radial-gradient(ellipse at 25% 50%, rgba(8, 13, 27, 0.6) 0%, rgba(8, 13, 27, 0.25) 60%, rgba(8, 13, 27, 0.75) 100%)',
          pointerEvents: 'none'
        }}
      />
    </div>
  );
};

export default Cinematic3DBackground;
