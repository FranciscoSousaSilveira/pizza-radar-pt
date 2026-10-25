/**
 * Pizza Radar PT — Fundo Reativo de Fatias de Pizza
 * Fatias de pizza em miniatura flutuantes com repulsão ao rato e ondas sonares de radar ao clicar.
 * 60 FPS, acelerado por hardware, sem dependências, desativa com prefers-reduced-motion.
 */
(function() {
  'use strict';

  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    return;
  }

  const canvas = document.getElementById('ambient-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  let width = 0;
  let height = 0;
  let dpr = 1;

  const mouse = {
    x: -1000,
    y: -1000,
    targetX: -1000,
    targetY: -1000,
    isHovered: false
  };

  const ripples = [];
  const sparks = [];
  const slices = [];
  const SLICE_COUNT = 30;

  class PizzaSlice {
    constructor() {
      this.reset(true);
    }

    reset(initial = false) {
      this.x = Math.random() * width;
      this.y = initial ? Math.random() * height : height + 25;
      this.size = 10 + Math.random() * 8; // Tamanho ideal de miniatura
      this.vx = (Math.random() - 0.5) * 0.35;
      this.vy = -(0.2 + Math.random() * 0.4); // Flutuação suave para cima
      this.alpha = 0.22 + Math.random() * 0.22;
      this.rotation = Math.random() * Math.PI * 2;
      this.vRot = (Math.random() - 0.5) * 0.015; // Rotação lenta e orgânica

      this.repelX = 0;
      this.repelY = 0;
    }

    update() {
      this.x += this.vx;
      this.y += this.vy;
      this.rotation += this.vRot;

      // Interação reativa com a proximidade do cursor (repulsão fluida)
      const dx = this.x - mouse.x;
      const dy = this.y - mouse.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const maxDist = 140;

      if (dist < maxDist && dist > 1) {
        const force = (1 - dist / maxDist) * 3.8;
        this.repelX += (dx / dist) * force;
        this.repelY += (dy / dist) * force;
        this.rotation += (dx > 0 ? 0.03 : -0.03); // Pequeno rodopio ao ser empurrada
      }

      this.x += this.repelX;
      this.y += this.repelY;
      this.repelX *= 0.88;
      this.repelY *= 0.88;

      if (this.y < -35 || this.x < -40 || this.x > width + 40) {
        this.reset();
      }
    }

    draw() {
      ctx.save();
      ctx.translate(this.x, this.y);
      ctx.rotate(this.rotation);

      const w = this.size;
      const h = this.size * 1.45;

      // 1. Corpo da fatia (queijo dourado com arco curvo)
      ctx.beginPath();
      ctx.moveTo(0, h * 0.5);
      ctx.lineTo(-w, -h * 0.5);
      ctx.quadraticCurveTo(0, -h * 0.62, w, -h * 0.5);
      ctx.lineTo(0, h * 0.5);
      ctx.closePath();
      ctx.fillStyle = `rgba(245, 158, 11, ${this.alpha})`;
      ctx.fill();

      // 2. Côdea cozida no topo
      ctx.beginPath();
      ctx.moveTo(-w * 1.05, -h * 0.5);
      ctx.quadraticCurveTo(0, -h * 0.66, w * 1.05, -h * 0.5);
      ctx.lineWidth = Math.max(2, this.size * 0.26);
      ctx.strokeStyle = `rgba(217, 119, 6, ${this.alpha * 1.15})`;
      ctx.lineCap = 'round';
      ctx.stroke();

      // 3. Rodelas de Pepperoni
      const pepR = Math.max(1.8, this.size * 0.2);
      ctx.fillStyle = `rgba(225, 29, 72, ${this.alpha * 1.2})`;
      ctx.beginPath();
      ctx.arc(-w * 0.28, -h * 0.15, pepR, 0, Math.PI * 2);
      ctx.fill();

      if (this.size > 12) {
        ctx.beginPath();
        ctx.arc(w * 0.22, h * 0.1, pepR * 0.85, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.restore();
    }
  }

  // Ondas radar pulsantes ao clicar
  class RadarRipple {
    constructor(x, y) {
      this.x = x;
      this.y = y;
      this.radius = 4;
      this.maxRadius = 140 + Math.random() * 40;
      this.alpha = 0.55;
      this.speed = 4.2;
    }

    update() {
      this.radius += this.speed;
      this.alpha = Math.max(0, 0.55 * (1 - (this.radius / this.maxRadius)));
    }

    draw() {
      if (this.alpha <= 0.01) return;
      ctx.save();
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(225, 29, 72, ${this.alpha})`;
      ctx.lineWidth = 1.8;
      ctx.stroke();

      if (this.radius > 25) {
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.radius * 0.65, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(245, 158, 11, ${this.alpha * 0.6})`;
        ctx.lineWidth = 1.2;
        ctx.stroke();
      }
      ctx.restore();
    }
  }

  // Faíscas suaves ao clicar
  class Spark {
    constructor(x, y) {
      this.x = x;
      this.y = y;
      const angle = Math.random() * Math.PI * 2;
      const speed = 2 + Math.random() * 4;
      this.vx = Math.cos(angle) * speed;
      this.vy = Math.sin(angle) * speed;
      this.radius = 2 + Math.random() * 2.5;
      this.alpha = 0.8;
      this.color = Math.random() > 0.4 ? 'rgba(225, 29, 72,' : 'rgba(245, 158, 11,';
    }

    update() {
      this.x += this.vx;
      this.y += this.vy;
      this.vx *= 0.94;
      this.vy *= 0.94;
      this.alpha -= 0.035;
    }

    draw() {
      if (this.alpha <= 0.01) return;
      ctx.save();
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
      ctx.fillStyle = `${this.color} ${this.alpha})`;
      ctx.fill();
      ctx.restore();
    }
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    ctx.scale(dpr, dpr);
  }

  function initSlices() {
    slices.length = 0;
    const count = width < 768 ? 16 : SLICE_COUNT;
    for (let i = 0; i < count; i++) {
      slices.push(new PizzaSlice());
    }
  }

  function addRipple(x, y) {
    ripples.push(new RadarRipple(x, y));
    const sparkCount = width < 768 ? 4 : 7;
    for (let i = 0; i < sparkCount; i++) {
      sparks.push(new Spark(x, y));
    }
  }

  window.addEventListener('resize', () => {
    resize();
    initSlices();
  }, { passive: true });

  window.addEventListener('mousemove', (e) => {
    mouse.targetX = e.clientX;
    mouse.targetY = e.clientY;
    mouse.isHovered = true;
  }, { passive: true });

  window.addEventListener('mouseleave', () => {
    mouse.isHovered = false;
  }, { passive: true });

  window.addEventListener('click', (e) => {
    addRipple(e.clientX, e.clientY);
  }, { passive: true });

  window.addEventListener('touchstart', (e) => {
    if (e.touches && e.touches[0]) {
      const touch = e.touches[0];
      mouse.targetX = touch.clientX;
      mouse.targetY = touch.clientY;
      mouse.isHovered = true;
      addRipple(touch.clientX, touch.clientY);
    }
  }, { passive: true });

  window.addEventListener('touchmove', (e) => {
    if (e.touches && e.touches[0]) {
      mouse.targetX = e.touches[0].clientX;
      mouse.targetY = e.touches[0].clientY;
      mouse.isHovered = true;
    }
  }, { passive: true });

  function animate() {
    if (mouse.isHovered) {
      mouse.x += (mouse.targetX - mouse.x) * 0.14;
      mouse.y += (mouse.targetY - mouse.y) * 0.14;
    }

    ctx.clearRect(0, 0, width, height);

    // Aura suave de calor que acompanha o rato
    if (mouse.isHovered && mouse.x > 0 && mouse.y > 0) {
      const glow = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, 220);
      glow.addColorStop(0, 'rgba(225, 29, 72, 0.045)');
      glow.addColorStop(0.5, 'rgba(245, 158, 11, 0.02)');
      glow.addColorStop(1, 'rgba(255, 255, 255, 0)');
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(mouse.x, mouse.y, 220, 0, Math.PI * 2);
      ctx.fill();
    }

    // Desenha as fatias de pizza flutuantes
    for (let i = 0; i < slices.length; i++) {
      slices[i].update();
      slices[i].draw();
    }

    // Ondas radar de clique
    for (let i = ripples.length - 1; i >= 0; i--) {
      ripples[i].update();
      ripples[i].draw();
      if (ripples[i].alpha <= 0.01) {
        ripples.splice(i, 1);
      }
    }

    // Faíscas de clique
    for (let i = sparks.length - 1; i >= 0; i--) {
      sparks[i].update();
      sparks[i].draw();
      if (sparks[i].alpha <= 0.01) {
        sparks.splice(i, 1);
      }
    }

    requestAnimationFrame(animate);
  }

  resize();
  initSlices();
  requestAnimationFrame(animate);
})();
