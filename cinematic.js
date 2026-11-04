'use strict';

// The homepage video uses one cancellable frame loop for each fade. Its loop
// point is handled explicitly so the last frame never flashes into the first.
document.addEventListener('DOMContentLoaded', () => {
  const menuToggle = document.querySelector('.nav-menu-toggle');
  menuToggle?.addEventListener('click', () => {
    const navbar = document.querySelector('.navbar');
    const open = navbar.classList.toggle('menu-open');
    menuToggle.setAttribute('aria-expanded', String(open));
    menuToggle.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
  });
  const video = document.getElementById('home-film');
  if (!video) return;
  let fadeFrame = 0;
  let fadeOutStarted = false;
  let restarting = false;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const canPlay = () => !reduced.matches && !document.hidden && window.STATE?.section === 'home';
  function syncPlayback() {
    if (canPlay()) video.play()?.catch(() => {});
    else { video.pause(); cancelAnimationFrame(fadeFrame); video.style.opacity = '1'; }
  }
  document.addEventListener('sylex:navigate', syncPlayback);
  document.addEventListener('visibilitychange', syncPlayback);
  reduced.addEventListener('change', syncPlayback);

  function fadeTo(target, duration = 500) {
    cancelAnimationFrame(fadeFrame);
    if (reduced.matches) {
      video.style.opacity = String(target);
      return;
    }
    const from = Number.parseFloat(video.style.opacity || '0') || 0;
    const start = performance.now();
    const frame = now => {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      video.style.opacity = String(from + (target - from) * eased);
      if (progress < 1) fadeFrame = requestAnimationFrame(frame);
    };
    fadeFrame = requestAnimationFrame(frame);
  }

  function restart() {
    if (restarting || !canPlay()) return;
    restarting = true;
    cancelAnimationFrame(fadeFrame);
    video.style.opacity = '0';
    window.setTimeout(() => {
      if (!canPlay()) { restarting = false; return; }
      video.currentTime = 0;
      fadeOutStarted = false;
      const play = video.play();
      if (play?.catch) play.catch(() => {});
      fadeTo(1);
      restarting = false;
    }, 100);
  }

  video.addEventListener('playing', () => {
    if (!fadeOutStarted && !restarting && Number(video.style.opacity || 0) < .1) fadeTo(1);
  });
  video.addEventListener('timeupdate', () => {
    if (!fadeOutStarted && Number.isFinite(video.duration) && video.duration - video.currentTime <= .55) {
      fadeOutStarted = true;
      fadeTo(0);
    }
  });
  video.addEventListener('ended', restart);
  video.addEventListener('error', () => { video.style.display = 'none'; });
  syncPlayback();
});
