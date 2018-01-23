from __future__ import print_function

import requests
import os
import urllib


import imp
import ast
import json

from simple_logger import log
import re

try:
    import discover_docker
    docker_available=True
except ImportError:
    docker_available=False

class AnalysisDelegatedException(Exception):
    def __init__(self,delegation_state):
        self.delegation_state=delegation_state

    def __repr__(self):
        return "[%s: %s]"%(self.__class__.__name__, self.data['delegation_state'])

class AnalysisException(Exception):
    @classmethod
    def from_ddosa_analysis_exceptions(cls,analysis_exceptions):
        obj=cls("found analysis exceptions", analysis_exceptions)
        obj.exceptions=[]
        for node_exception in analysis_exceptions:
            node,exception=re.match("\('(.*?)',(.*)\)",node_exception).groups()
            exception=exception.strip()

            obj.exceptions.append(dict(node=node,exception=exception,exception_kind="handled"))
        return obj

    @classmethod
    def from_ddosa_unhandled_exception(cls, unhandled_exception):
        obj = cls("found unhandled analysis exceptions", unhandled_exception)
        obj.exceptions = [dict([('kind',"unhandled")]+unhandled_exception.items())]
        return obj

    @classmethod
    def from_graph_exception(cls, graph_exception):
        obj = cls("found graph exception", graph_exception)
        obj.exceptions = [graph_exception]
        return obj

    def __repr__(self):
        r=super(AnalysisException,self)
        r+="\n\nembedded exceptions"
        for exception in self.exceptions:
            r+="in node %s: %s"(exception['node'],exception['exception'])
        return r

class WorkerException(Exception):
    def __init__(self,comment,content=None,product_exception=None,worker_output=None):
        self.comment=comment
        self.content=content
        self.product_exception=product_exception
        self.worker_output=worker_output

    def __repr__(self):
        r=self.__class__.__name__+": "+self.comment
        if self.worker_output:
            r+="\n\nWorker output:\n"+self.worker_output

    def display(self):
        log(repr(self))
        try:
            log(json.loads(self.content)['result']['output'])
        except Exception as e:
            log("detailed output display not easy")


class Secret(object):
    @property
    def secret_location(self):
        if 'DDOSA_SECRET' in os.environ:
            return os.environ['DDOSA_SECRET']
        else:
            return os.environ['HOME']+"/.secret-ddosa-client"

    def get_auth(self):
        username="remoteintegral" # keep separate from secrect to cause extra confusion!
        password=open(self.secret_location).read().strip()
        return requests.auth.HTTPBasicAuth(username, password)


class DDOSAproduct(object):
    def __init__(self,ddosa_worker_response,ddcache_root_local):
        self.ddcache_root_local=ddcache_root_local
        self.interpret_ddosa_worker_response(ddosa_worker_response)

    def interpret_ddosa_worker_response(self,r):
        self.raw_response=r

        log(self,r["result"])

        log("found result keys:",r.keys())

        try:
            #data=ast.literal_eval(repr(r['data']))
            data=r['data']
        except ValueError:
            log("failed to interpret data \"",r['data'],"\"")
            log(r['data'].__class__)
            log(r['data'].keys())
            open('tmp_data_dump.json','w').write(repr(r['data']))
            raise

        if r['exceptions']!=[] and r['exceptions']!='' and r['exceptions'] is not None:
            if r['exceptions']['exception_type']=="delegation":
                raise AnalysisDelegatedException(r['exceptions']['delegation_state'])
            raise AnalysisException.from_ddosa_unhandled_exception(r['exceptions'])

        if data is None:
            raise WorkerException("data is None, the analysis failed unexclicably")

        json.dump(data,open("data.json","w"), sort_keys=True, indent=4, separators=(',', ': '))
        log("jsonifiable data dumped to data.json")

        log("cached object in",r['cached_path'])

        for k,v in data.items():
            log("setting attribute",k)
            setattr(self,k,v)

            try:
                if v[0]=="DataFile":
                    local_fn=(r['cached_path'][0].replace("data/ddcache",self.ddcache_root_local)+"/"+v[1]).replace("//","/")+".gz"
                    log("data file attached:",k,local_fn)
                    setattr(self,k,local_fn)
            except Exception as e:
                pass

        if 'analysis_exceptions' in data and data['analysis_exceptions']!=[]:
            raise AnalysisException.from_ddosa_analysis_exceptions(data['analysis_exceptions'])



class RemoteDDOSA(object):
    default_modules=["git://ddosa","ddosadm"]
    default_assume=["ddosadm.DataSourceConfig(use_store_files=False)"] if not ('SCWDATA_SOURCE_MODULE' in os.environ and os.environ['SCWDATA_SOURCE_MODULE']=='ddosadm') else []

    def __init__(self,service_url,ddcache_root_local):
        self.service_url=service_url
        self.ddcache_root_local=ddcache_root_local

        self.secret=Secret()

    @property
    def service_url(self):
        return self._service_url

    @service_url.setter
    def service_url(self,service_url):
        if service_url is None:
            raise Exception("service url can not be None!")
        
        adapter=service_url.split(":")[0]
        if adapter not in ["http"]:
            raise Exception("adapter %s not allowed!"%adapter)
        self._service_url=service_url

    def prepare_request(self,target,modules=[],assume=[],inject=[],prompt_delegate=False,callback=None):
        log("modules", ",".join(modules))
        log("assume", ",".join(assume))
        log("service url:",self.service_url)
        log("target:", target)
        log("inject:",inject)

        if prompt_delegate:
            api_version = "v2.0"
        else:
            api_version = "v1.0"

        args=dict(url=self.service_url+"/api/"+api_version+"/"+target,
                    params=dict(modules=",".join(self.default_modules+modules),
                                assume=",".join(self.default_assume+assume),
                                inject=json.dumps(inject),
                                ))

        if callback is not None:
            args['params']['callback']=callback
        
        if 'OPENID_TOKEN' in os.environ:
            args['params']['token']=os.environ['OPENID_TOKEN']

        return args


    def poke(self):
        return self.query("poke")

    def query(self,target,modules=[],assume=[],inject=[],prompt_delegate=False,callback=None):
        try:
            p=self.prepare_request(target,modules,assume,inject,prompt_delegate,callback)
            log("request to pipeline:",p)
            log("request to pipeline:",p['url']+"/"+urllib.urlencode(p['params']))
            response=requests.get(p['url'],p['params'],auth=self.secret.get_auth())
        except Exception as e:
            log("exception in request",e,logtype="error")
            raise

        try:
            response_json=response.json()
            return DDOSAproduct(response_json,self.ddcache_root_local)
        except WorkerException as e:
        #except Exception as e:
            log("exception exctacting json:",e)
            log("raw content: ",response.content,logtype="error")
            open("tmp_response_content.txt","w").write(response.content)
            worker_output=None
            if "result" in response.json():
                if "output" in response.json()['result']:
                    worker_output=response.json()['result']['output']
                    open("tmp_response_content_result_output.txt", "w").write(worker_output)

            open("tmp_response_content.txt", "w").write(response.content)
            raise WorkerException("no json was produced!",content=response.content,worker_output=worker_output,product_exception=e)
        except Exception as e:
            log("exception decoding json:", e)
            log("raw content: ", response.content, logtype="error")
            open("tmp_response_content.txt", "w").write(response.content)
            raise

    def __repr__(self):
        return "[%s: direct %s]"%(self.__class__.__name__,self.service_url)

class AutoRemoteDDOSA(RemoteDDOSA):

    def from_docker(self,config_version):
        if config_version == "docker_any" and docker_available:
            c = discover_docker.DDOSAWorkerContainer()

            url = c.url
            ddcache_root_local = c.ddcache_root
            log("managed to read from docker:")
            return url,ddcache_root_local
        raise Exception("not possible to access docker")

    def from_env(self,config_version):
        url = os.environ['DDOSA_WORKER_URL']
        ddcache_root_local = os.environ['INTEGRAL_DDCACHE_ROOT']
        return url, ddcache_root_local

    def from_config(self,config_version):
        if config_version is None:
            if 'DDOSA_WORKER_VERSION' in os.environ:
                config_version = os.environ['DDOSA_WORKER_VERSION']
            else:
                config_version = "devel"

        log("from config:", config_version)

        if config_version == "":
            config_suffix = ''
        else:
            config_suffix = '_' + config_version

        config_fn = '/home/isdc/savchenk/etc/ddosa-docker/config%s.py' % config_suffix
        log(":", config_fn)

        ddosa_config = imp.load_source('ddosa_config', config_fn)

        ddcache_root_local = ddosa_config.ddcache_root_local
        url = ddosa_config.url

        return url, ddcache_root_local

    def discovery_methods(self):
        return [
                    'from_env',
                    'from_config',
            ]


    def __init__(self,config_version=None):

        methods_tried=[]
        result=None
        for method in self.discovery_methods():

            try:
                result=getattr(self,method)(config_version)
            except Exception as e:
                methods_tried.append((method,e))

        if result is None:
            raise Exception("all docker discovery methods failed, tried "+repr(methods_tried))

        url, ddcache_root_local = result


        log("url:",url)
        log("ddcache_root:",ddcache_root_local)

        super(AutoRemoteDDOSA,self).__init__(url,ddcache_root_local)



class HerdedDDOSA(RemoteDDOSA):
    def __repr__(self):
        return "[%s: herder %s]"%(self.__class__.__name__,self.service_url)

    def query(self):
        raise Exception("not implemented!")

