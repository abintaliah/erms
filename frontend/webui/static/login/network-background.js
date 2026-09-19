(() => {
  const SELECTOR = '.wathiq-network-canvas';
  const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)');
  const instances = new WeakMap();

  function createNetwork(canvas) {
    const context = canvas.getContext('2d');
    if (!context) return null;
    const compact = canvas.classList.contains('wathiq-header-network');

    const state = {
      width: 0,
      height: 0,
      nodes: [],
      animationFrame: null,
      resizeObserver: null,
    };
    const palette = ['#268bd2', '#69b4df', '#f1b642'];

    function resize() {
      const box = canvas.getBoundingClientRect();
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      state.width = box.width;
      state.height = box.height;
      canvas.width = Math.max(1, Math.round(state.width * ratio));
      canvas.height = Math.max(1, Math.round(state.height * ratio));
      context.setTransform(ratio, 0, 0, ratio, 0, 0);

      const count = compact
        ? Math.max(12, Math.min(30, Math.round(state.width / 55)))
        : Math.max(28, Math.min(58, Math.round(state.width / 28)));
      state.nodes = Array.from({ length: count }, (_, index) => ({
        x: Math.random() * state.width,
        y: compact
          ? 4 + Math.random() * Math.max(1, state.height - 8)
          : 54 + Math.random() * Math.max(1, state.height - 88),
        vx: (Math.random() - 0.5) * (compact ? 0.12 : 0.18),
        vy: (Math.random() - 0.5) * (compact ? 0.08 : 0.18),
        radius: index % 9 === 0 ? (compact ? 2.4 : 3.5) : (compact ? 1.4 : 2),
      }));
      draw(false);
    }

    function isVisible() {
      return canvas.isConnected && canvas.getClientRects().length > 0;
    }

    function draw(advance = true) {
      context.clearRect(0, 0, state.width, state.height);

      if (advance) {
        for (const node of state.nodes) {
          node.x += node.vx;
          node.y += node.vy;
          if (node.x < -20) node.x = state.width + 20;
          if (node.x > state.width + 20) node.x = -20;
          const topBoundary = compact ? 2 : 54;
          const bottomBoundary = compact ? state.height - 2 : state.height - 34;
          if (node.y < topBoundary) node.y = bottomBoundary;
          if (node.y > bottomBoundary) node.y = topBoundary;
        }
      }

      const connectionDistance = compact ? 105 : 150;
      for (let index = 0; index < state.nodes.length; index += 1) {
        for (let otherIndex = index + 1; otherIndex < state.nodes.length; otherIndex += 1) {
          const first = state.nodes[index];
          const second = state.nodes[otherIndex];
          const distance = Math.hypot(first.x - second.x, first.y - second.y);
          if (distance >= connectionDistance) continue;
          context.beginPath();
          context.moveTo(first.x, first.y);
          context.lineTo(second.x, second.y);
          context.strokeStyle = `rgba(38, 139, 210, ${(1 - distance / connectionDistance) * (compact ? 0.13 : 0.22)})`;
          context.lineWidth = compact ? 0.65 : 0.8;
          context.stroke();
        }
      }

      state.nodes.forEach((node, index) => {
        context.beginPath();
        context.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
        context.fillStyle = palette[index % palette.length];
        context.globalAlpha = index % 9 === 0
          ? (compact ? 0.42 : 0.75)
          : (compact ? 0.24 : 0.45);
        context.fill();
      });
      context.globalAlpha = 1;
    }

    function animate() {
      state.animationFrame = null;
      if (!isVisible()) return;
      draw(!REDUCED_MOTION.matches && !document.hidden);
      if (!REDUCED_MOTION.matches && !document.hidden) {
        state.animationFrame = window.requestAnimationFrame(animate);
      }
    }

    function start() {
      if (!isVisible()) return;
      const box = canvas.getBoundingClientRect();
      if (state.width !== box.width || state.height !== box.height) resize();
      if (!state.animationFrame) animate();
    }

    function stop() {
      if (state.animationFrame) window.cancelAnimationFrame(state.animationFrame);
      state.animationFrame = null;
    }

    state.resizeObserver = new ResizeObserver(() => {
      resize();
      start();
    });
    state.resizeObserver.observe(canvas);
    resize();
    start();
    return { start, stop };
  }

  function synchronize() {
    document.querySelectorAll(SELECTOR).forEach((canvas) => {
      let instance = instances.get(canvas);
      if (!instance) {
        instance = createNetwork(canvas);
        if (instance) instances.set(canvas, instance);
      }
      if (canvas.getClientRects().length > 0) instance?.start();
      else instance?.stop();
    });
  }

  new MutationObserver(synchronize).observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['class', 'style'],
  });
  document.addEventListener('visibilitychange', synchronize);
  REDUCED_MOTION.addEventListener('change', synchronize);
  window.addEventListener('load', synchronize, { once: true });
  window.startWathiqLoginNetwork = synchronize;
  synchronize();
})();
