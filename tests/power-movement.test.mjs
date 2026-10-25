import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { Vector3 } from '@babylonjs/core/Maths/math.vector.js';
import { makeCollision, PLAYER_R } from '../src/powerMovement.ts';
const meta = JSON.parse(readFileSync(new URL('../public/models/power/power_room.json', import.meta.url)));
const move = makeCollision(meta);
function free(p) {
  for (const c of meta.colliders) assert.ok(Math.hypot(p.x+c.x,p.z+c.y) >= c.r+PLAYER_R-1e-6, `inside collider ${JSON.stringify(c)}`);
  assert.ok(p.x >= -meta.walk.maxX+PLAYER_R-1e-6 && p.x <= -meta.walk.minX-PLAYER_R+1e-6);
  assert.ok(p.z >= -meta.walk.maxY+PLAYER_R-1e-6 && p.z <= -meta.walk.minY-PLAYER_R+1e-6);
}
const spawn = () => new Vector3(-meta.spawn.x, 0, -meta.spawn.y);
test('power spawn and central route remain clear with rebuilt machinery',()=>{
  const p=spawn();free(p);move(p,0,-.9);free(p);assert.ok(p.z<0);
});
test('power reactor stops long movements; front pit cannot be entered',()=>{
  const p=spawn();move(p,-.25,0);move(p,0,-20);free(p);assert.ok(p.z>-1.5);
  move(p,0,30);free(p);assert.ok(p.z<=1.08+1e-6);
});
test('power side equipment and corners permit sliding without penetration',()=>{
  for(const direction of [[1,0],[-1,0],[1,1],[-1,1],[1,-1],[-1,-1]]){
    const p=spawn();
    for(let i=0;i<250;i++){move(p,direction[0]*.04,direction[1]*.04);free(p);}
  }
});
