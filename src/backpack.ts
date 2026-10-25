import { Companions, PETS, PetId } from './companions';

const STYLE_ID = 'petbag-style';
const CSS = `
#petbag{position:fixed;right:18px;bottom:78px;z-index:45;font-family:inherit;color:#eaf8ff;
  -webkit-user-select:none;user-select:none;}
#petbag *{box-sizing:border-box;}
#petbag .pb-toggle{position:relative;width:58px;height:58px;border-radius:19px;cursor:pointer;
  display:flex;align-items:center;justify-content:center;padding:0;
  background:linear-gradient(160deg,rgba(14,52,86,.94),rgba(3,15,28,.96));
  border:1px solid rgba(122,220,255,.45);
  box-shadow:0 8px 26px rgba(0,0,0,.42),inset 0 0 20px rgba(70,190,255,.14);
  transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease;}
#petbag .pb-toggle:hover{transform:translateY(-2px);border-color:rgba(158,238,255,.85);
  box-shadow:0 10px 30px rgba(0,0,0,.48),0 0 22px rgba(80,200,255,.28),inset 0 0 22px rgba(90,210,255,.2);}
#petbag .pb-toggle img{width:44px;height:44px;object-fit:contain;pointer-events:none;
  filter:drop-shadow(0 2px 4px rgba(0,0,0,.5));}
#petbag .pb-toggle .pb-key{position:absolute;right:-5px;top:-5px;min-width:18px;height:18px;padding:0 4px;
  border-radius:6px;background:rgba(120,225,255,.92);color:#03202f;font-size:11px;font-weight:700;
  line-height:18px;text-align:center;box-shadow:0 2px 6px rgba(0,0,0,.4);}
#petbag .pb-label{position:absolute;right:66px;top:50%;transform:translateY(-50%);white-space:nowrap;
  font-size:12px;letter-spacing:1px;color:#bdeaff;background:rgba(3,18,32,.72);
  border:1px solid rgba(110,210,255,.25);border-radius:10px;padding:5px 10px;pointer-events:none;
  opacity:0;transition:opacity .18s ease;}
#petbag .pb-toggle:hover+.pb-label{opacity:1;}
#petbag .pb-panel{position:absolute;right:0;bottom:70px;width:302px;padding:14px 14px 12px;
  border-radius:20px;opacity:0;transform:translateY(10px) scale(.98);pointer-events:none;
  transform-origin:bottom right;transition:opacity .2s ease,transform .2s ease;
  background:linear-gradient(165deg,rgba(9,37,62,.97),rgba(2,11,21,.98));
  border:1px solid rgba(110,215,255,.36);
  box-shadow:0 22px 60px rgba(0,0,0,.55),inset 0 1px 0 rgba(180,240,255,.14),0 0 34px rgba(40,150,230,.14);}
#petbag.open .pb-panel{opacity:1;transform:translateY(0) scale(1);pointer-events:auto;}
#petbag .pb-head{display:flex;align-items:center;justify-content:space-between;margin:0 2px 10px;}
#petbag .pb-title{font-size:15px;font-weight:700;letter-spacing:2px;color:#d8f5ff;}
#petbag .pb-title small{display:block;margin-top:2px;font-size:10px;font-weight:400;letter-spacing:1.5px;
  color:#6ea6c4;text-transform:uppercase;}
#petbag .pb-nono{display:flex;align-items:center;gap:7px;font-size:11px;color:#9fe5ff;
  border:1px solid rgba(95,205,255,.3);border-radius:999px;padding:4px 9px 4px 5px;
  background:rgba(20,80,120,.35);}
#petbag .pb-nono img{width:20px;height:20px;object-fit:contain;}
#petbag .pb-nono i{width:6px;height:6px;border-radius:50%;background:#63f0c8;
  box-shadow:0 0 8px #63f0c8;animation:pb-dot 2.2s ease-in-out infinite;}
@keyframes pb-dot{0%,100%{opacity:.55}50%{opacity:1}}
#petbag .pb-grid{display:grid;grid-template-columns:1fr 1fr;gap:9px;}
#petbag .pb-item{position:relative;display:flex;align-items:center;gap:9px;padding:8px 9px;cursor:pointer;
  border-radius:14px;border:1px solid rgba(105,185,230,.18);
  background:linear-gradient(150deg,rgba(18,52,80,.62),rgba(6,22,38,.62));
  transition:border-color .16s ease,background .16s ease,transform .16s ease;}
#petbag .pb-item:hover{transform:translateY(-1px);border-color:rgba(135,225,255,.55);
  background:linear-gradient(150deg,rgba(24,70,105,.75),rgba(7,28,48,.75));}
#petbag .pb-item.active{border-color:rgba(105,230,255,.9);
  background:linear-gradient(150deg,rgba(24,96,136,.8),rgba(8,40,66,.82));
  box-shadow:0 0 0 1px rgba(105,230,255,.25),0 0 20px rgba(60,190,255,.28),inset 0 0 18px rgba(60,190,255,.14);}
#petbag .pb-item img{width:46px;height:46px;object-fit:contain;flex:0 0 auto;
  filter:drop-shadow(0 2px 4px rgba(0,0,0,.45));}
#petbag .pb-name{font-size:13px;font-weight:600;color:#e8f9ff;line-height:1.2;}
#petbag .pb-tag{display:block;margin-top:3px;font-size:10px;color:#7fb2cc;letter-spacing:1px;}
#petbag .pb-item.active .pb-tag{color:#8fe6ff;}
#petbag .pb-check{position:absolute;right:7px;top:7px;width:14px;height:14px;border-radius:50%;
  background:#6ce7ff;color:#04212f;font-size:9px;font-weight:900;line-height:14px;text-align:center;
  opacity:0;transform:scale(.5);transition:opacity .16s,transform .16s;}
#petbag .pb-item.active .pb-check{opacity:1;transform:scale(1);}
#petbag .pb-foot{margin:11px 2px 0;font-size:10px;letter-spacing:.5px;color:#5f93ad;display:flex;
  justify-content:space-between;}
#petbag .pb-foot b{color:#8fd9f5;font-weight:600;}
@media (max-width:640px){
  #petbag{right:12px;bottom:70px;}
  #petbag .pb-panel{width:272px;}
  #petbag .pb-toggle{width:52px;height:52px;border-radius:17px;}
  #petbag .pb-toggle img{width:40px;height:40px;}
}
`;

export interface Backpack {
  open(): void;
  close(): void;
  toggle(): void;
  readonly isOpen: boolean;
  dispose(): void;
}

export function createBackpack(companions: Companions): Backpack {
  if (!document.getElementById(STYLE_ID)) {
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = CSS;
    document.head.appendChild(style);
  }

  const root = document.createElement('div');
  root.id = 'petbag';
  root.innerHTML = `
    <div class="pb-panel" role="dialog" aria-label="精灵背包">
      <div class="pb-head">
        <div class="pb-title">精灵背包<small>PET PACK</small></div>
        <div class="pb-nono"><img src="/ui/pets/super_nono.png" alt=""><i></i>超能NONO 跟随中</div>
      </div>
      <div class="pb-grid"></div>
      <div class="pb-foot"><span>点击切换跟随宠物</span><span><b>B</b> 开 / 关</span></div>
    </div>
    <button class="pb-toggle" type="button" aria-label="打开精灵背包" aria-expanded="false"></button>
    <div class="pb-label">精灵背包 · B</div>
  `;
  document.body.appendChild(root);

  const toggleBtn = root.querySelector<HTMLButtonElement>('.pb-toggle')!;
  const grid = root.querySelector<HTMLElement>('.pb-grid')!;

  const items = new Map<PetId, HTMLElement>();
  for (const pet of PETS) {
    const el = document.createElement('button');
    el.type = 'button';
    el.className = 'pb-item';
    el.dataset.pet = pet.id;
    el.innerHTML = `
      <img src="${pet.icon}" alt="${pet.name}" draggable="false">
      <span><span class="pb-name"></span><span class="pb-tag"></span></span>
      <span class="pb-check">✓</span>
    `;
    el.querySelector('.pb-name')!.textContent = pet.name;
    el.querySelector('.pb-tag')!.textContent = pet.element;
    el.addEventListener('click', () => {
      companions.setPet(pet.id);
      sync();
    });
    grid.appendChild(el);
    items.set(pet.id, el);
  }

  let openState = false;

  const sync = () => {
    const id = companions.current;
    for (const [pid, el] of items) el.classList.toggle('active', pid === id);
    const icon = PETS.find((p) => p.id === id)!.icon;
    toggleBtn.innerHTML = `<img src="${icon}" alt="${PETS.find((p) => p.id === id)!.name}"><span class="pb-key">B</span>`;
    toggleBtn.setAttribute('aria-label', `精灵背包（当前：${PETS.find((p) => p.id === id)!.name}）`);
  };

  const setOpen = (v: boolean) => {
    openState = v;
    root.classList.toggle('open', v);
    toggleBtn.setAttribute('aria-expanded', String(v));
  };

  toggleBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    setOpen(!openState);
  });

  const onKey = (e: KeyboardEvent) => {
    const target = e.target as HTMLElement | null;
    if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
    if (e.code === 'KeyB' && !e.repeat) {
      e.preventDefault();
      setOpen(!openState);
    } else if (e.code === 'Escape' && openState) {
      setOpen(false);
    }
  };
  const onDown = (e: PointerEvent) => {
    if (openState && !root.contains(e.target as Node)) setOpen(false);
  };
  window.addEventListener('keydown', onKey);
  document.addEventListener('pointerdown', onDown);

  sync();
  setOpen(false);

  const api: Backpack = {
    open: () => setOpen(true),
    close: () => setOpen(false),
    toggle: () => setOpen(!openState),
    get isOpen() {
      return openState;
    },
    dispose: () => {
      window.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onDown);
      root.remove();
    },
  };
  (window as unknown as { __petbag?: Backpack }).__petbag = api;
  return api;
}
