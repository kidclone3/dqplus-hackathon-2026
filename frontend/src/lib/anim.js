import gsap from 'gsap';

export const prefersReduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export function riseIn(scope, selector = '.rise') {
  if (!scope || prefersReduced()) return;
  const targets = scope.querySelectorAll ? scope.querySelectorAll(selector) : [];
  if (!targets.length) return;
  gsap.from(targets, {
    y: 18,
    autoAlpha: 0,
    duration: 0.5,
    ease: 'power2.out',
    stagger: 0.06,
    clearProps: 'all',
  });
}
