import { Scene, UniversalCamera, Vector3 } from '@babylonjs/core';
import { EYE_HEIGHT, floorHeight, moveInRoom, type RoomCollision } from './inventionMovement';

/** 鼠标锁定优先；内嵌浏览器不支持时仍能拖动查看。 */
export function createFirstPersonCamera(scene: Scene, canvas: HTMLCanvasElement, collision: RoomCollision) {
  const camera = new UniversalCamera('firstPersonCamera', new Vector3(0, EYE_HEIGHT, 4.6), scene);
  camera.setTarget(new Vector3(0, 1.75, -5.5));
  camera.minZ = 0.07;
  camera.maxZ = 2400;
  camera.fov = 0.95;
  camera.inertia = 0;
  // 只使用下面的输入控制，避免内置键盘运动绕过设备碰撞。
  camera.inputs.clear();
  canvas.tabIndex = 0;
  canvas.setAttribute('aria-label', '发明室第一人称画面，WASD移动，鼠标查看');
  canvas.style.touchAction = 'none';

  const reticle = document.createElement('div');
  reticle.className = 'fps-reticle';
  reticle.setAttribute('aria-hidden', 'true');
  const help = document.createElement('button');
  help.className = 'fps-help';
  help.type = 'button';
  help.textContent = '点击画面进入 · WASD 移动';
  help.setAttribute('aria-label', '进入第一人称鼠标控制');
  document.body.append(reticle, help);

  const keys = new Set<string>();
  const movementKeys = new Set(['KeyW', 'KeyA', 'KeyS', 'KeyD', 'ArrowUp', 'ArrowLeft', 'ArrowDown', 'ArrowRight', 'ShiftLeft', 'ShiftRight']);
  const listeners = new AbortController();
  const signal = listeners.signal;
  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  let dragDistance = 0;
  let fallback = false;
  const locked = () => document.pointerLockElement === canvas;
  const updateHelp = () => {
    help.textContent = locked() ? 'WASD 移动 · Shift 快走 · Esc 释放鼠标' : fallback ? '按住画面拖动查看 · WASD 移动' : '点击画面进入 · WASD 移动';
    help.classList.toggle('is-locked', locked());
  };
  const enter = async () => {
    canvas.focus({ preventScroll: true });
    if (locked()) return;
    try {
      if (!canvas.requestPointerLock) throw new Error('pointer lock unavailable');
      await canvas.requestPointerLock();
    } catch {
      fallback = true;
      updateHelp();
    }
  };
  const look = (dx: number, dy: number) => {
    camera.rotation.y += dx * 0.0022;
    camera.rotation.x = Math.max(-1.35, Math.min(1.35, camera.rotation.x + dy * 0.0022));
    camera.rotation.z = 0;
  };
  help.addEventListener('click', () => void enter(), { signal });
  canvas.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    canvas.focus({ preventScroll: true });
    dragging = true;
    dragDistance = 0;
    lastX = event.clientX;
    lastY = event.clientY;
    if (!locked()) canvas.setPointerCapture(event.pointerId);
  }, { signal });
  canvas.addEventListener('pointermove', (event) => {
    if (locked() || !dragging) return;
    const dx = event.clientX - lastX;
    const dy = event.clientY - lastY;
    lastX = event.clientX;
    lastY = event.clientY;
    dragDistance += Math.abs(dx) + Math.abs(dy);
    look(dx, dy);
  }, { signal });
  canvas.addEventListener('pointerup', (event) => {
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    if (dragging && dragDistance < 4 && event.pointerType !== 'touch') void enter();
    dragging = false;
  }, { signal });
  canvas.addEventListener('pointercancel', () => { dragging = false; }, { signal });
  document.addEventListener('mousemove', (event) => {
    if (locked()) look(event.movementX, event.movementY);
  }, { signal });
  document.addEventListener('pointerlockchange', () => {
    keys.clear();
    dragging = false;
    updateHelp();
  }, { signal });
  document.addEventListener('pointerlockerror', () => { fallback = true; updateHelp(); }, { signal });
  window.addEventListener('keydown', (event) => {
    if (!movementKeys.has(event.code) || event.metaKey || event.ctrlKey || event.altKey) return;
    if (!locked() && document.activeElement !== canvas) return;
    event.preventDefault();
    keys.add(event.code);
  }, { signal });
  window.addEventListener('keyup', (event) => keys.delete(event.code), { signal });
  window.addEventListener('blur', () => { keys.clear(); dragging = false; }, { signal });
  document.addEventListener('visibilitychange', () => { if (document.hidden) keys.clear(); }, { signal });

  const observer = scene.onBeforeRenderObservable.add(() => {
    const dt = Math.min(scene.getEngine().getDeltaTime() / 1000, 0.05);
    const forward = Number(keys.has('KeyW') || keys.has('ArrowUp')) - Number(keys.has('KeyS') || keys.has('ArrowDown'));
    const strafe = Number(keys.has('KeyD') || keys.has('ArrowRight')) - Number(keys.has('KeyA') || keys.has('ArrowLeft'));
    const length = Math.hypot(forward, strafe);
    if (length > 0) {
      const speed = keys.has('ShiftLeft') || keys.has('ShiftRight') ? 4.8 : 3;
      const step = speed * dt / length;
      const yaw = camera.rotation.y;
      const pos = moveInRoom(camera.position, (Math.sin(yaw) * forward + Math.cos(yaw) * strafe) * step,
        (Math.cos(yaw) * forward - Math.sin(yaw) * strafe) * step, collision);
      camera.position.x = pos.x;
      camera.position.z = pos.z;
    }
    // 平稳踏上两层台阶，不加入强制镜头晃动或跑步变焦。
    const targetY = EYE_HEIGHT + floorHeight(camera.position.x, camera.position.z);
    camera.position.y += (targetY - camera.position.y) * Math.min(1, dt * 12);
  });
  scene.onDisposeObservable.addOnce(() => {
    listeners.abort();
    scene.onBeforeRenderObservable.remove(observer);
    if (locked()) document.exitPointerLock();
    reticle.remove();
    help.remove();
  });
  return camera;
}
