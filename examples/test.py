

import json
import ast
import ddaclient as dc
import discover_docker
import imp

try:
    c=discover_docker.DDOSAWorkerContainer()

    url=c.url
    ddcache_root_local=c.ddcache_root
    print("managed to read from docker:")
except Exception as e:
    print("failed to read from docker, will try config:")

    ddosa_config = imp.load_source('ddosa_config', '/home/isdc/savchenk/etc/ddosa-docker/config.py')

    ddcache_root_local=ddosa_config.ddcache_root_local
    url=ddosa_config.url

print("url:",url)
print("ddcache_root:",ddcache_root_local)

r=dc.RemoteDDOSA(url)\
        .query(target="ii_skyimage",
               modules=["ddosa","git://ddosadm"],
               assume=['ddosa.ScWData(input_scwid="035200230010.001")',
                       'ddosa.ImageBins(use_ebins=[(20,40)],use_version="onebin_20_40")',
                       'ddosa.ImagingConfig(use_SouFit=0,use_version="soufit0")'])

print(r["result"])

print(list(r.keys()))

data=ast.literal_eval(str(r['data']))
        
json.dump(data,open("data.json","w"), sort_keys=True, indent=4, separators=(',', ': '))
print("jsonifiable data dumped to data.json")

print("cached object in",r['cached_path'])

for k,v in list(data.items()):
    try:
        if v[0]=="DataFile":
            print("data file attached:",k,(r['cached_path'][0].replace("data/ddcache",ddcache_root_local)+"/"+v[1]).replace("//","/")+".gz")
    except:
        # not iterable, or empty file
        pass
