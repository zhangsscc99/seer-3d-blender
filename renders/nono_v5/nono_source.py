"""参考图 NONO：青色半球圆顶头、几乎占满正面的黑色面罩、双短竖眼、身后扁平裙翼和细长 V 形耳翼。

独立审核（不触碰场景资产）：
  Blender -b -P blender/nono.py -- --out renders/nono_v1
build_nono 可由房间生成器复用；正面朝 Blender -Y。
"""
import math
import sys
from pathlib import Path
import bpy
import bmesh
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
    shell=material('nono_shell',(.11,.6,.72),.36,.02,.22)
    shell.node_tree.nodes['Principled BSDF'].inputs['Subsurface Weight'].default_value=.12
    edge=material('nono_rim',(.55,.93,.96),.25,0,.6)
    dark=material('nono_visor',(.001,.023,.032),.31,0)
    visor_bs=dark.node_tree.nodes['Principled BSDF']
    visor_bs.inputs['Coat Weight'].default_value=.025
    visor_bs.inputs['Specular IOR Level'].default_value=.18
    eye=material('nono_eyes',(.26,.85,.91),.26,0,1.2)
    objects=[]

    def mesh(name,verts,faces,mat):
        data=bpy.data.meshes.new(prefix+'_'+name)
        data.from_pydata(verts,[],faces)
        data.update()
        # 焊接叶片端点，统一外向法线；面罩是开放曲面，正面必须朝 -Y。
        bm=bmesh.new()
        bm.from_mesh(data)
        bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-6)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        if (name == 'visor' and sum(f.normal.y*f.calc_area() for f in bm.faces)>0) or (name != 'visor' and bm.calc_volume(signed=True)<0):
            bmesh.ops.reverse_faces(bm,faces=list(bm.faces))
        bm.to_mesh(data)
        bm.free()
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

    def ellipsoid(name,c,rx,ry,rzt,rzb,mat,seg=64,rings=32):
        # 上下半轴不同的椭球：上半圆顶、下半压扁。
        verts=[(c[0],c[1],c[2]+rzt)]
        for i in range(1,rings):
            th=math.pi*i/rings;z=math.cos(th);s=math.sin(th)
            for j in range(seg):
                a=j*math.tau/seg
                verts.append((c[0]+rx*s*math.cos(a),c[1]+ry*s*math.sin(a),c[2]+z*(rzt if z>0 else rzb)))
        verts.append((c[0],c[1],c[2]-rzb))
        last=len(verts)-1
        faces=[(0,1+j,1+(j+1)%seg) for j in range(seg)]
        for i in range(rings-2):
            a=1+i*seg;b=a+seg
            faces.extend((a+j,b+j,b+(j+1)%seg,a+(j+1)%seg) for j in range(seg))
        a=1+(rings-2)*seg
        faces.extend((a+(j+1)%seg,a+j,last) for j in range(seg))
        return mesh(name,verts,faces,mat)

    # 半球圆顶头：参考三处都是宽于高的圆顶，底部平直。
    HX,HY,HZT,HZB=.33,.28,.30,.075
    ellipsoid('shell',(0,0,0),HX,HY,HZT,HZB,shell)
    # 身后向两侧展开的扁平透镜状裙翼（培养管正视最清楚）。
    ellipsoid('skirt',(0,.10,.06),.62,.22,.20,.09,shell)

    def front(x,z,offset=0):
        rz=HZT if z>0 else HZB
        y=-HY*math.sqrt(max(.0004,1-(x/HX)**2-(z/rz)**2))
        return (x,y-.006-offset,z)

    # 面罩：几乎占满正面的半圆拱，只留细青边；底边略下垂、圆角过渡。
    boundary=[]
    for i in range(48):
        th=math.pi*i/47
        c=math.cos(th);s=abs(math.sin(th))
        boundary.append((.29*math.copysign(abs(c)**.85,c),.012+.262*s**1.1))
    for i in range(1,24):
        x=-.29+.58*i/24
        boundary.append((x,.012-.03*(1-(x/.29)**2)**.6))
    CX,CZ=0,.11
    n=len(boundary);rings=12
    verts=[front(CX,CZ)]
    for k in range(1,rings+1):
        r=k/rings
        verts.extend(front(CX+(x-CX)*r,CZ+(z-CZ)*r) for x,z in boundary)
    faces=[(0,1+(j+1)%n,1+j) for j in range(n)]
    for k in range(rings-1):
        a=1+k*n;b=a+n
        faces.extend((a+j,a+(j+1)%n,b+(j+1)%n,b+j) for j in range(n))
    mesh('visor',verts,faces,dark)
    curve('visor_rim',[front(x,z,.002) for x,z in boundary],.005,edge,True)
    # 面罩底部的亮白唇边（中央特写最明显）。
    curve('chin',[front(x,z,.004) for x,z in boundary[47:]+[boundary[0]]],.011,edge)
    for side in (-1,1):
        # 两只眼睛是短而粗的竖直灯条，位于面罩中部偏上。
        pts=[front(side*.11,.06+j/12*.16,.014) for j in range(13)]
        curve('eye_'+str(side),pts,.035,eye)
        for i in (0,-1):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,radius=.035,location=pts[i])
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
        # 细长 V 形耳翼：从圆顶后上方伸出，约 45° 外展，长度超过头高。
        leaf('ear_'+str(side),[(.07,.08,.27),(.20,.10,.36),(.40,.11,.50),(.60,.12,.62)],.058,.02,side)

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
    # 三个实景姿态单独出图，使用同一模型，逐个对照原图。
    for o in objects:bpy.data.objects.remove(o,do_unlink=True)
    cam.location=(.15,-5,2.0)
    cam.rotation_euler=(Vector((0,0,.16))-cam.location).to_track_quat('-Z','Y').to_euler()
    for label,yaw,bank in [('pod_pose',.40,-.24),('center_pose',.18,-.34),('tube_pose',0,0)]:
        posed=build_nono(prefix=label,yaw=yaw,bank=bank)
        scene.render.filepath=str(out/(label+'.png'))
        bpy.ops.render.render(write_still=True)
        for o in posed:bpy.data.objects.remove(o,do_unlink=True)
    print('NONO review ready:',out)

if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    preview(args[args.index('--out')+1] if '--out' in args else 'renders/nono_review')
