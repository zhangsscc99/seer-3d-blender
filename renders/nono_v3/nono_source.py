"""参考图 NONO：青色梨形一体机身、黑色面罩、双竖条眼和上扬的叶片耳翼。

独立审核（不触碰场景资产）：
  Blender -b -P blender/nono.py -- --out renders/nono_v1
build_nono 可由房间生成器复用；正面朝 Blender -Y。
"""
import math
import sys
from pathlib import Path
import bpy
from mathutils import Vector


def material(name, color, roughness=.3, metallic=0, emission=0):
    m=bpy.data.materials.get(name)
    if m:
        return m
    m=bpy.data.materials.new(name)
    m.use_nodes=True
    bs=m.node_tree.nodes['Principled BSDF']
    bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Metallic'].default_value=metallic
    bs.inputs['Roughness'].default_value=roughness
    bs.inputs['Coat Weight'].default_value=.2
    bs.inputs['Emission Color'].default_value=(*color,1)
    bs.inputs['Emission Strength'].default_value=emission
    return m


def build_nono(prefix='nono', origin=(0,0,0), scale=1, yaw=0, bank=0, pitch=-.12):
    shell=material('nono_shell',(.07,.66,.72),.24,.02,.22)
    shell.node_tree.nodes['Principled BSDF'].inputs['Subsurface Weight'].default_value=.12
    edge=material('nono_rim',(.15,.81,.86),.25,0,.35)
    dark=material('nono_visor',(.001,.023,.032),.25,0)
    eye=material('nono_eyes',(.26,.85,.91),.26,0,1.2)
    objects=[]

    def mesh(name,verts,faces,mat):
        data=bpy.data.meshes.new(prefix+'_'+name)
        data.from_pydata(verts,[],faces)
        data.update()
        o=bpy.data.objects.new(prefix+'_'+name,data)
        bpy.context.collection.objects.link(o)
        data.materials.append(mat)
        for p in data.polygons:
            p.use_smooth=True
        objects.append(o)
        return o

    def curve(name,pts,r,mat,closed=False):
        data=bpy.data.curves.new(prefix+'_'+name,'CURVE')
        data.dimensions='3D'
        data.bevel_depth=r
        data.bevel_resolution=3
        sp=data.splines.new('POLY')
        sp.points.add(len(pts)-1)
        for p,co in zip(sp.points,pts):
            p.co=(*co,1)
        sp.use_cyclic_u=closed
        o=bpy.data.objects.new(prefix+'_'+name,data)
        bpy.context.collection.objects.link(o)
        data.materials.append(mat)
        objects.append(o)
        return o

    # 椭圆截面软锥体：窄圆顶、外扩的下侧缘，避免旧版的圆球头盔轮廓。
    profile=[(-.34,.035,.09),(-.31,.24,.19),(-.25,.40,.28),
             (-.16,.51,.32),(-.04,.475,.33),(.09,.40,.31),
             (.22,.30,.26),(.32,.19,.19),(.39,.075,.10),(.41,.002,.005)]

    def section(z):
        for k in range(len(profile)-1):
            if z <= profile[k+1][0]:
                a=profile[max(0,k-1)];b=profile[k];c=profile[k+1];d=profile[min(len(profile)-1,k+2)]
                t=max(0,(z-b[0])/(c[0]-b[0]))
                values=[]
                for j in (1,2):
                    mb=(c[j]-a[j])/(c[0]-a[0])*(c[0]-b[0])
                    mc=(d[j]-b[j])/(d[0]-b[0])*(c[0]-b[0])
                    values.append((2*t**3-3*t*t+1)*b[j]+(t**3-2*t*t+t)*mb+(-2*t**3+3*t*t)*c[j]+(t**3-t*t)*mc)
                return values
        return profile[-1][1:]

    verts=[]
    rows,cols=64,64
    for i in range(rows+1):
        z=-.34+i/rows*.75
        rx,ry=section(z)
        for j in range(cols):
            a=j*math.tau/cols
            verts.append((rx*math.cos(a),ry*math.sin(a),z))
    faces=[]
    for i in range(rows):
        for j in range(cols):
            k=i*cols+j;n=i*cols+(j+1)%cols
            faces.append((k,n,n+cols,k+cols))
    faces.extend([tuple(reversed(range(cols))),tuple(rows*cols+j for j in range(cols))])
    mesh('shell',verts,faces,shell)

    # 光滑曲面面罩：穹顶轮廓，宽而平缓的下沿。
    boundary=[]
    curves=[
        ((.255,-.225),(.34,-.215),(.342,-.14),(.307,-.035)),
        ((.307,-.035),(.255,.14),(.115,.355),(0,.355)),
        ((0,.355),(-.115,.355),(-.255,.14),(-.307,-.035)),
        ((-.307,-.035),(-.342,-.14),(-.34,-.215),(-.255,-.225)),
        ((-.255,-.225),(-.13,-.258),(.13,-.258),(.255,-.225)),
    ]
    for a,b,c,d in curves:
        for i in range(20):
            t=i/20;u=1-t
            boundary.append(tuple(u**3*a[k]+3*u*u*t*b[k]+3*u*t*t*c[k]+t**3*d[k] for k in range(2)))
    def front(x,z,offset=0):
        rx,ry=section(z)
        y=-ry*math.sqrt(max(.015,1-(x/rx)**2))
        return (x,y-.009-offset,z)
    verts=[front(0,.025)]
    n=len(boundary)
    rings=10
    for k in range(1,rings+1):
        r=k/rings
        for x,z in boundary:
            verts.append(front(x*r,.025+(z-.025)*r))
    faces=[(0,1+(j+1)%n,1+j) for j in range(n)]
    for k in range(rings-1):
        a=1+k*n; b=a+n
        for j in range(n):
            q=(j+1)%n
            faces.append((a+j,a+q,b+q,b+j))
    mesh('visor',verts,faces,dark)
    curve('visor_rim',[front(x,z,.002) for x,z in boundary],.004,edge,True)
    for side in (-1,1):
        # 两只眼睛是竖直窄灯条，无单眼镜头或瞳孔。
        pts=[front(side*.112-.014*(j/12-.5),-.065+j/12*.24,.014) for j in range(13)]
        curve('eye_'+str(side),pts,.021,eye)
        for i in (0,-1):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,radius=.021,location=pts[i])
            cap=bpy.context.active_object
            # 顶点归入同一局部坐标，后续统一烘焙放置变换。
            for v in cap.data.vertices:v.co+=cap.location
            cap.location=(0,0,0)
            cap.name=f'{prefix}_eye_cap_{side}_{i}'
            cap.data.materials.append(eye)
            for poly in cap.data.polygons:poly.use_smooth=True
            objects.append(cap)

    def leaf(name,control,width,depth,side):
        # 弯曲的锥形薄鳍，靠根部丰满、末端收尖，避免对称纺锤叶片。
        verts=[]
        steps,sections=28,16
        p0,p1,p2,p3=map(Vector,control)
        for i in range(steps+1):
            t=i/steps;u=1-t
            center=u**3*p0+3*u*u*t*p1+3*u*t*t*p2+t**3*p3
            tangent=3*u*u*(p1-p0)+6*u*t*(p2-p1)+3*t*t*(p3-p2)
            normal=Vector((-tangent.z,0,tangent.x)).normalized()
            taper=(math.sin(math.pi*t)**.65)*(1-.38*t)
            for j in range(sections):
                a=j*math.tau/sections
                v=center+normal*(width*taper*math.cos(a))+Vector((0,depth*taper*math.sin(a),0))
                verts.append((v.x*side,v.y,v.z))
        faces=[]
        for i in range(steps):
            for j in range(sections):
                k=i*sections+j;q=i*sections+(j+1)%sections
                faces.append((k,q,q+sections,k+sections) if side==1 else (k,k+sections,q+sections,q))
        mesh(name,verts,faces,shell)

    for side in (-1,1):
        leaf('ear_'+str(side),[(.13,.02,.335),(.25,.045,.42),(.45,.02,.57),(.52,-.015,.76)],.09,.024,side)
        leaf('flipper_'+str(side),[(.38,.005,-.14),(.49,-.03,-.20),(.57,-.06,-.22),(.62,-.08,-.21)],.052,.026,side)

    # 曲线转网格；变换直接烘进每个顶点，使 room 动画前缀分组可靠。
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:
        if o.type=='CURVE':
            bpy.context.view_layer.objects.active=o
            o.select_set(True)
            bpy.ops.object.convert(target='MESH')
            o.select_set(False)
        for v in o.data.vertices:
            x,y,z=v.co
            y,z=y*math.cos(pitch)-z*math.sin(pitch),y*math.sin(pitch)+z*math.cos(pitch)
            x,z=x*math.cos(bank)+z*math.sin(bank),-x*math.sin(bank)+z*math.cos(bank)
            v.co=(origin[0]+scale*(x*math.cos(yaw)-y*math.sin(yaw)),
                  origin[1]+scale*(x*math.sin(yaw)+y*math.cos(yaw)),origin[2]+scale*z)
    return objects


def preview(out):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objects=build_nono()
    scene=bpy.context.scene
    world=bpy.data.worlds.new('studio')
    scene.world=world
    world.use_nodes=True
    world.node_tree.nodes['Background'].inputs[0].default_value=(.11,.17,.20,1)
    world.node_tree.nodes['Background'].inputs[1].default_value=.5
    for name,loc,power,size in [('key',(-3,-4,5),350,4),('fill',(4,-2,2),150,3),('rim',(0,3,4),250,3)]:
        ld=bpy.data.lights.new(name,'AREA');ld.energy=power;ld.shape='DISK';ld.size=size
        ob=bpy.data.objects.new(name,ld);bpy.context.collection.objects.link(ob);ob.location=loc
        ob.rotation_euler=(-ob.location).to_track_quat('-Z','Y').to_euler()
    camera=bpy.data.cameras.new('review_camera')
    camera.type='ORTHO';camera.ortho_scale=1.95
    cam=bpy.data.objects.new('review_camera',camera);bpy.context.collection.objects.link(cam)
    scene.camera=cam
    scene.render.engine='CYCLES';scene.cycles.samples=32
    scene.cycles.use_denoising=True
    scene.render.resolution_x=800;scene.render.resolution_y=800;scene.render.resolution_percentage=100
    scene.view_settings.view_transform='AgX'
    scene.render.image_settings.file_format='PNG'
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    for label,loc in [('front',(0,-5,.2)),('reference',(.45,-5,2.1)),('three_quarter',(3,-5,1.6))]:
        cam.location=loc
        cam.rotation_euler=(Vector((0,0,.16))-cam.location).to_track_quat('-Z','Y').to_euler()
        scene.render.filepath=str(out/(label+'.png'))
        bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'nono.blend'))
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(out/'nono.glb'),export_format='GLB',use_selection=True,export_apply=True)
    print('NONO review ready:',out)

if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    preview(args[args.index('--out')+1] if '--out' in args else 'renders/nono_review')
