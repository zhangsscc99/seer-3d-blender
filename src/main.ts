export {};
const params = new URLSearchParams(location.search);
const which = params.get('scene') ?? 'kelosi';

const nav = document.getElementById('nav');
if (nav) {
  for (const [id, label] of [
    ['kelosi', '克洛斯星'],
    ['station', '赛尔号空间站'],
    ['invention', '发明室 I'],
    ['power', '动力室 I'],
    ['teleport', '传送舱 I'],
    ['lookout', '瞭望露台 I'],
  ]) {
    const a = document.createElement('a');
    a.textContent = label;
    a.href = `?scene=${id}`;
    if (id === which) a.className = 'on';
    nav.appendChild(a);
  }
}

if (which === 'station') await import('./station');
else if (which === 'invention') await import('./invention');
else if (which === 'power') await import('./power');
else if (which === 'teleport') await import('./teleport');
else if (which === 'lookout') await import('./lookout');
else await import('./kelosi');
