/**
 * Pizza Radar PT — Motor de Fundo Interativo & Reativo
 * Cria partículas ambientais culinárias, brilho dinâmico do cursor e ondas radar sonares ao clicar.
 * 60 FPS, acelerado por hardware, sem dependências, desativa com prefers-reduced-motion.
 */
(function() {
  'use strict';

  // Respeita utilizadores com preferência de movimento reduzido
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

  // Estado do cursor
  const mouse = {
    x: -1000,
    y: -1000,
    targetX: -1000,
    targetY: -1000,
    isHovered: false
  };

  // Ondas radar ativas geradas por cliques
  const ripples = [];

  // Partículas de faísca / sabor emitidas no clique
  const sparks = [];

  // Partículas flutuantes de fundo
  const particles = [];
  const PARTICLE_COUNT = 32;

  const COLORS = {
    crust: 'rgba(234, 88, 12, ',       // Laranja quente
    tomato: 'rgba(225, 29, 72, ',      // Vermelho vivo
    basil: 'rgba(22, 163, 74, ',       // Verde manjericão
    cheese: 'rgba(245, 158, 11, ',     // Dourado mozzarella
    radar: 'rgba(225, 29, 72, '        // Vermelho radar
  };

  const SHAPES = ['circle', 'ring', 'slice', 'star'];

  class Particle {
    constructor() {
      this.reset(true);
    }

    reset(initial = false) {
      this.x = Math.random() * width;
      this.y = initial ? Math.random() * height : height + 20;
      this.size = 3 + Math.random() * 6;
      this.vx = (Math.random() - 0.5) * 0.4;
      this.vy = -(0.2 + Math.random() * 0.35); // Flutuação suave para cima
      this.shape = SHAPES[Math.floor(Math.random() * SHAPES.length)];

      const keys = Object.keys(COLORS);
      this.colorBase = COLORS[keys[Math.floor(Math.random() * keys.length)]];
      this.alpha = 0.12 + Math.random() * 0.18;
      this.rotation = Math.random() * Math.PI * 2;
      this.vRot = (Math.random() - 0.5) * 0.015;

      // Deslocamento por repulsão do rato
      this.repelX = 0;
      this.repelY = 0;
    }

    update() {
      this.x += this.vx;
      this.y += this.vy;
      this.rotation += this.vRot;

      // Interação reativa com a posição do rato (repulsão fluida estilo líquido)
      const dx = this.x - mouse.x;
      const dy = this.y - mouse.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const maxDist = 130;

      if (dist < maxDist && dist > 1) {
        const force = (1 - dist / maxDist) * 3.5;
        this.repelX += (dx / dist) * force;
        this.repelY += (dy / dist) * force;
      }

      // Aplica repulsão com amortecimento suave
      this.x += this.repelX;
      this.y += this.repelY;
      this.repelX *= 0.88;
      this.repelY *= 0.88;

      // Reposiciona quando sai do ecrã
      if (this.y < -30 || this.x < -40 || this.x > width + 40) {
        this.reset();
      }
    }

    draw() {
      ctx.save();
      ctx.translate(this.x, this.y);
      ctx.rotate(this.rotation);
      ctx.fillStyle = this.colorBase + this.alpha + ')';
      ctx.strokeStyle = this.colorBase + (this.alpha * 1.2) + ')';
      ctx.lineWidth = 1.2;

      if (this.shape === 'circle') {
        ctx.beginPath();
        ctx.arc(0, 0, this.size, 0, Math.PI * 2);
        ctx.fill();
      } else if (this.shape === 'ring') {
        ctx.beginPath();
        ctx.arc(0, 0, this.size * 1.2, 0, Math.PI * 2);
        ctx.stroke();
      } else if (this.shape === 'slice') {
        // Pequena fatia triangular estilizada
        ctx.beginPath();
        ctx.moveTo(0, -this.size * 1.3);
        ctx.lineTo(this.size, this.size);
        ctx.lineTo(-this.size, this.size);
        ctx.closePath();
        ctx.fill();
      } else if (this.shape === 'star') {
        // Ponto de brilho / estrela
        ctx.beginPath();
        ctx.arc(0, 0, this.size * 0.7, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.restore();
    }
  }

  // Ondas radar pulsantes no clique
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

      // Eco de segunda onda interior
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

  // Faíscas efervescentes no clique
  class Spark {
    constructor(x, y) {
      this.x = x;
      this.y = y;
      const angle = Math.random() * Math.PI * 2;
      const speed = 2 + Math.random() * 5;
      this.vx = Math.cos(angle) * speed;
      this.vy = Math.sin(angle) * speed;
      this.radius = 2 + Math.random() * 3;
      this.alpha = 0.85;
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

  function initParticles() {
    particles.length = 0;
    const count = width < 768 ? 18 : PARTICLE_COUNT;
    for (let i = 0; i < count; i++) {
      particles.push(new Particle());
    }
  }

  function addRipple(x, y) {
    ripples.push(new RadarRipple(x, y));
    // Cria 6-8 partículas de faísca ao clicar
    const sparkCount = width < 768 ? 5 : 8;
    for (let i = 0; i < sparkCount; i++) {
      sparks.push(new Spark(x, y));
    }
  }

  // Event Listeners de interação
  window.addEventListener('resize', () => {
    resize();
    initParticles();
  }, { passive: true });

  window.addEventListener('mousemove', (e) => {
    mouse.targetX = e.clientX;
    mouse.targetY = e.clientY;
    mouse.isHovered = true;
  }, { passive: true });

  window.addEventListener('mouseleave', () => {
    mouse.isHovered = false;
  }, { passive: true });

  // Disparo reativo ao clique
  window.addEventListener('click', (e) => {
    addRipple(e.clientX, e.clientY);
  }, { passive: true });

  // Suporte a toque no telemóvel
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

  // Loop de Animação a 60 FPS
  function animate() {
    // Interpolação fluida da posição do rato
    if (mouse.isHovered) {
      mouse.x += (mouse.targetX - mouse.x) * 0.14;
      mouse.y += (mouse.targetY - mouse.y) * 0.14;
    }

    ctx.clearRect(0, 0, width, height);

    // Brilho de cursor suave (Aura dinâmica que segue o rato)
    if (mouse.isHovered && mouse.x > 0 && mouse.y > 0) {
      const glow = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, 240);
      glow.addColorStop(0, 'rgba(225, 29, 72, 0.05)');
      glow.addColorStop(0.5, 'rgba(245, 158, 11, 0.025)');
      glow.addColorStop(1, 'rgba(255, 255, 255, 0)');
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(mouse.x, mouse.y, 240, 0, Math.PI * 2);
      ctx.fill();
    }

    // Atualiza e desenha partículas flutuantes
    for (let i = 0; i < particles.length; i++) {
      particles[i].update();
      particles[i].draw();
    }

    // Ondas sonares de clique
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

  // Inicialização
  resize();
  initParticles();
  requestAnimationFrame(animate);
})();
