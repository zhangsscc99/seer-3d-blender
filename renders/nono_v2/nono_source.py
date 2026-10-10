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


def build_nono(prefix='nono', origin=(0,0,0), scale=1, yaw=0, bank=0):
    shell=material('nono_shell',(.12,.67,.72),.31,.12,.16)
    edge=material('nono_rim',(.15,.72,.76),.32,.1,.16)
    dark=material('nono_visor',(.002,.021,.03),.36,0)
    eye=material('nono_eyes',(.32,.86,.92),.3,0,1.1)
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

    # 机身从窄圆顶向下变宽，底部收圆；没有分开的头、躯干或机械赤道环。
    verts=[]
    rows,cols=40,64
    for i in range(rows+1):
        t=math.pi*i/rows
        z=.405*math.cos(t)
        if z < 0: z *= .84
        rx=.44*math.sin(t)*(1-.22*math.cos(t))
        ry=.32*math.sin(t)
        for j in range(cols):
            a=j*math.tau/cols
            verts.append((rx*math.cos(a),ry*math.sin(a),z))
    faces=[]
    for i in range(rows):
        for j in range(cols):
            k=i*cols+j; n=i*cols+(j+1)%cols
            faces.append((k,n,n+cols,k+cols))
    mesh('shell',verts,faces,shell)

    # 光滑曲面面罩：穹顶轮廓，宽而平缓的下沿。
    boundary=[]
    curves=[
        ((.27,-.235),(.34,-.23),(.35,-.16),(.31,-.055)),
        ((.31,-.055),(.265,.14),(.135,.295),(0,.295)),
        ((0,.295),(-.135,.295),(-.265,.14),(-.31,-.055)),
        ((-.31,-.055),(-.35,-.16),(-.34,-.23),(-.27,-.235)),
        ((-.27,-.235),(-.12,-.26),(.12,-.26),(.27,-.235)),
    ]
    for a,b,c,d in curves:
        for i in range(20):
            t=i/20;u=1-t
            boundary.append(tuple(u**3*a[k]+3*u*u*t*b[k]+3*u*t*t*c[k]+t**3*d[k] for k in range(2)))
    def front(x,z,offset=0):
        c=max(-.99,min(.99,z/(.405 if z>=0 else .405*.84)))
        rx=.44*math.sqrt(1-c*c)*(1-.22*c)
        y=-.32*math.sqrt(max(.025,1-c*c))*math.sqrt(max(.015,1-(x/rx)**2))
        return (x,y-.012-offset,z)
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
    curve('visor_rim',[front(x,z,.002) for x,z in boundary],.005,edge,True)
    for side in (-1,1):
        # 两只眼睛是竖直窄灯条，无单眼镜头或瞳孔。
        pts=[front(side*.10-.024*(j/12-.5),-.075+j/12*.235,.017) for j in range(13)]
        curve('eye_'+str(side),pts,.016,eye)
        for i in (0,-1):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,radius=.016,location=pts[i])
            cap=bpy.context.active_object
            # 顶点归入同一局部坐标，后续统一烘焙放置变换。
            for v in cap.data.vertices:v.co+=cap.location
            cap.location=(0,0,0)
            cap.name=f'{prefix}_eye_cap_{side}_{i}'
            cap.data.materials.append(eye)
            for poly in cap.data.polygons:poly.use_smooth=True
            objects.append(cap)

    def leaf(name,start,end,width,depth,side):
        verts=[]
        steps,sections=20,12
        direction=Vector(end)-Vector(start)
        normal=Vector((-direction.z,0,direction.x)).normalized()
        for i in range(steps+1):
            t=i/steps
            center=Vector(start).lerp(Vector(end),t)
            center.y+=.075*math.sin(math.pi*t)
            taper=math.sin(math.pi*t)**.8
            for j in range(sections):
                a=j*math.tau/sections
                v=center+normal*(width*taper*math.cos(a))+Vector((0,depth*taper*math.sin(a),0))
                verts.append((v.x*side,v.y,v.z))
        faces=[]
        for i in range(steps):
            for j in range(sections):
                k=i*sections+j; q=i*sections+(j+1)%sections
                faces.append((k,q,q+sections,k+sections) if side==1 else (k,k+sections,q+sections,q))
        mesh(name,verts,faces,shell)

    for side in (-1,1):
        leaf('ear_'+str(side),(.19,.055,.30),(.79,.10,.67),.061,.020,side)
        leaf('flipper_'+str(side),(.33,.08,-.21),(.46,.15,-.30),.038,.020,side)

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
