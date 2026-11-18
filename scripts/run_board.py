#!/usr/bin/env python3
"""Execute one audited FFN notebook stage through an existing, authorized local Jupyter tunnel."""
import argparse
import getpass
import os
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import uuid
import zipfile

import requests
import websocket

ROOT=Path(__file__).resolve().parents[1]
RELEASES={'B11':'B11_20261118T204214272606Z_audit3','K44':'K44_20261118T205854106482Z_audit3'}
STAGES=['preflight','program','control','buffers','smoke','validate','benchmark','close','cpu','files']
TIMEOUTS=[30,45,20,20,20,60,180,20,180,20]

class Run:
    def __init__(self,config,board,deadline,run_id):
        if deadline.tzinfo is None:
            raise ValueError('Reservation end must include a UTC offset')
        if Path(run_id).name != run_id or run_id in ('.','..'):
            raise ValueError('Run ID must be a simple directory name')
        if board not in (1,2,3):
            raise ValueError('Expected a course board number from 1 to 3')
        self.board=board
        self.end=deadline
        self.config=config
        self.release=RELEASES[config]
        self.out=ROOT/'results/board_runs'/run_id/config
        self.out.mkdir(parents=True,exist_ok=True)
        self.state_file=self.out/'remote_run.json'
        self.state=json.loads(self.state_file.read_text()) if self.state_file.exists() else None
        if self.state is not None:
            if self.state['board']!=board or self.state['config']!=config or self.state['reservation_end']!=deadline.isoformat():
                raise RuntimeError('Existing run belongs to a different board, configuration, or reservation')
        self.nb_file=self.out/'ffn_board_executed.ipynb'
        self.nb=json.loads(self.nb_file.read_text()) if self.nb_file.exists() else None
        self.base='http://127.0.0.1:{}'.format(9090+board)
        if datetime.now(timezone.utc)>=self.end: raise RuntimeError('Board reservation ended')
        password=os.environ.get('PYNQ_PASSWORD')
        if not password:
            if not sys.stdin.isatty():
                raise RuntimeError('Set PYNQ_PASSWORD locally or use an interactive terminal; do not commit credentials')
            password=getpass.getpass('PYNQ Jupyter password: ')
        self.http=requests.Session();self.http.trust_env=False
        self.http.get(self.base+'/login',timeout=10).raise_for_status()
        self.http.post(self.base+'/login',data={'_xsrf':self.http.cookies.get('_xsrf'),'password':password},timeout=10).raise_for_status()
        self.http.headers['X-XSRFToken']=self.http.cookies.get('_xsrf')

    def persist(self):
        if self.state is not None: self.state_file.write_text(json.dumps(self.state,indent=2)+'\n')
        if self.nb is not None: self.nb_file.write_text(json.dumps(self.nb,indent=1)+'\n')

    def log(self,text):
        line=datetime.now(timezone.utc).isoformat()+' '+text
        print(line,flush=True)
        with (self.out/'execution.log').open('a') as f: f.write(line+'\n')

    def api(self,method,path,**kwargs):
        if datetime.now(timezone.utc)>=self.end: raise RuntimeError('Board reservation ended')
        r=self.http.request(method,self.base+'/api/'+path,timeout=15,**kwargs)
        r.raise_for_status()
        return r.json() if r.content else None

    def execute(self,code,timeout,cell=None):
        if (self.end-datetime.now(timezone.utc)).total_seconds()<timeout+60:
            raise RuntimeError('Insufficient reserved time for this operation and saving')
        sid=uuid.uuid4().hex;mid=uuid.uuid4().hex
        cookie='; '.join(c.name+'='+c.value for c in self.http.cookies)
        ws=websocket.create_connection(self.base.replace('http:','ws:')+'/api/kernels/'+self.state['kernel_id']+'/channels?session_id='+sid,
            cookie=cookie,origin=self.base,timeout=8)
        message={'header':{'msg_id':mid,'username':'ffn-runner','session':sid,'date':datetime.now(timezone.utc).isoformat(),'msg_type':'execute_request','version':'5.3'},
            'parent_header':{},'metadata':{},'channel':'shell','buffers':[],
            'content':{'code':code,'silent':False,'store_history':True,'user_expressions':{},'allow_stdin':False,'stop_on_error':True}}
        failure=None;deadline=time.monotonic()+timeout;last=time.monotonic()
        try:
            ws.send(json.dumps(message))
            while time.monotonic()<deadline:
                try: raw=ws.recv()
                except websocket.WebSocketTimeoutException:
                    if time.monotonic()-last>20:
                        self.log('Still waiting for this stage; no additional operation queued.')
                        last=time.monotonic()
                    continue
                m=json.loads(raw)
                if m.get('parent_header',{}).get('msg_id')!=mid: continue
                kind=m['header']['msg_type'];c=m['content']
                if kind=='execute_input' and cell is not None: cell['execution_count']=c['execution_count']
                elif kind=='stream':
                    self.log(c['text'].rstrip())
                    if cell is not None: cell['outputs'].append({'output_type':'stream','name':c['name'],'text':c['text']})
                elif kind in ('display_data','execute_result'):
                    self.log(c['data'].get('text/plain','Display output'))
                    if cell is not None:
                        out={'output_type':kind,'data':c['data'],'metadata':c.get('metadata',{})}
                        if kind=='execute_result': out['execution_count']=c['execution_count']
                        cell['outputs'].append(out)
                elif kind=='error':
                    failure=c['ename']+': '+c['evalue'];self.log('\n'.join(c.get('traceback',[])))
                    if cell is not None: cell['outputs'].append(dict(output_type='error',ename=c['ename'],evalue=c['evalue'],traceback=c['traceback']))
                elif kind=='execute_reply' and c.get('status')=='error': failure=c['ename']+': '+c['evalue']
                elif kind=='status' and c['execution_state']=='idle':
                    if failure: raise RuntimeError(failure)
                    return
                self.persist()
            raise TimeoutError('Stage completion unknown: kernel/buffers retained; do not interrupt/reprogram')
        finally:
            ws.close();self.persist()

    def setup(self):
        if self.state is not None: raise RuntimeError('Run already exists')
        existing=self.api('GET','kernels')
        if existing: raise RuntimeError('Existing kernels found; establish ownership before programming')
        kernel=self.api('POST','kernels',json={'name':'python3'})
        self.state={'board':self.board,'config':self.config,'kernel_id':kernel['id'],'reservation_end':self.end.isoformat(),
                    'started_utc':datetime.now(timezone.utc).isoformat(),'completed':[]}
        self.persist()
        health='''import os,sys,json,platform,subprocess
from pathlib import Path
import pynq
manager=Path('/sys/class/fpga_manager/fpga0/state')
health={'hostname':platform.node(),'machine':platform.machine(),'python':sys.version,'pynq':pynq.__version__,
        'allocate_available':hasattr(pynq,'allocate'),'BOARD':os.environ.get('BOARD'),
        'model':Path('/proc/device-tree/model').read_text().strip('\\x00') if Path('/proc/device-tree/model').exists() else 'not exposed',
        'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'fpga_manager':manager.read_text().strip() if manager.exists() else 'not exposed',
        'loadavg':Path('/proc/loadavg').read_text().strip(),
        'cpuinfo':Path('/proc/cpuinfo').read_text(),
        'meminfo':Path('/proc/meminfo').read_text(),
        'compiler':subprocess.check_output(['g++','--version'],universal_newlines=True)}
guard=Path('/tmp/ece506_ffn.state.json')
health['prior_ffn_guard']=guard.read_text() if guard.exists() else None
health['kernel_log_before']=subprocess.check_output(['dmesg'],universal_newlines=True).splitlines()[-45:]
print(json.dumps(health,indent=2),flush=True)
if health['hostname']!=EXPECTED_HOST or health['machine']!='armv7l': raise RuntimeError('Wrong board')
if 'error' in health['fpga_manager'].lower(): raise RuntimeError('FPGA manager already reports an error')
if not health['allocate_available']: raise RuntimeError('PYNQ allocate API unavailable')
'''
        try:
            self.execute(health.replace('EXPECTED_HOST',repr('pynq'+str(self.board))),30)
            self.state['completed'].append('health')
            remote='ffn_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+self.config
            archive=(ROOT/'deploy'/(self.release+'.zip')).read_bytes()
            self.api('PUT','contents/'+remote,json={'type':'directory'})
            self.api('PUT','contents/'+remote+'/release.zip',json={'type':'file','format':'base64','content':base64.b64encode(archive).decode()})
            self.state['remote_directory']=remote
            self.state['zip_sha256']=hashlib.sha256(archive).hexdigest()
            with zipfile.ZipFile(io.BytesIO(archive)) as package:
                self.nb=json.loads(package.read(self.release+'/ffn_board.ipynb'))
            self.persist()
            bootstrap='''import zipfile,hashlib
from pathlib import Path
candidates=[Path.cwd()/REMOTE,Path('/home/xilinx/jupyter_notebooks')/REMOTE,Path('/home/xilinx')/REMOTE]
work=next(p for p in candidates if (p/'release.zip').exists())
archive=work/'release.zip'
if hashlib.sha256(archive.read_bytes()).hexdigest()!=EXPECTED: raise RuntimeError('Upload hash mismatch')
with zipfile.ZipFile(archive) as z: z.extractall(str(work))
os.chdir(str(work/RELEASE))
Path('board_environment.json').write_text(json.dumps(health,indent=2)+'\\n')
print('UPLOAD_VERIFIED:',os.getcwd(),flush=True)
'''.replace('REMOTE',repr(remote)).replace('EXPECTED',repr(self.state['zip_sha256'])).replace('RELEASE',repr(self.release))
            self.execute(bootstrap,30)
            self.state['completed'].append('setup');self.log('SETUP_PASS; FPGA not programmed')
        except BaseException as e:
            self.state['failure']='setup: '+repr(e);raise
        finally: self.persist()

    def stage(self,name):
        if self.state is None or 'setup' not in self.state['completed']: raise RuntimeError('Setup required')
        if self.state.get('failure') or self.state.get('active_stage'): raise RuntimeError('Earlier operation failed or completion unknown')
        i=STAGES.index(name);previous='setup' if i==0 else STAGES[i-1]
        if previous not in self.state['completed'] or name in self.state['completed']: raise RuntimeError('Wrong stage order')
        cell=[c for c in self.nb['cells'] if c['cell_type']=='code'][i]
        self.state['active_stage']=name;self.persist();self.log('START '+name)
        try:
            self.execute(''.join(cell['source']),TIMEOUTS[i],cell)
            self.state['completed'].append(name);self.state.pop('active_stage');self.log('PASS '+name)
        except BaseException as e:
            self.state['failure']=name+': '+repr(e);raise
        finally: self.persist()
        self.save_notebook()

    def save_notebook(self):
        path=self.state['remote_directory']+'/'+self.release+'/ffn_board_executed.ipynb'
        self.api('PUT','contents/'+path,json={'type':'notebook','format':'json','content':self.nb})

    def collect(self):
        if not self.state or not self.state.get('remote_directory'): raise RuntimeError('Nothing uploaded')
        prefix='contents/'+self.state['remote_directory']+'/'+self.release+'/'
        for name in ['manifest.json','board_environment.json','load_stages.jsonl','board_validation.json','board_raw.csv',
                     'board_results.json','cpu_run.log','cpu_raw.csv','cpu_results.json',
                     'board_profile.json','board_profile_raw.csv','board_health_after.json']:
            try: model=self.api('GET',prefix+name,params={'format':'base64'})
            except requests.HTTPError as e:
                if e.response.status_code==404: continue
                raise
            (self.out/name).write_bytes(base64.b64decode(model['content']))
            self.log('SAVED '+name)
        self.save_notebook()

    def finish(self):
        if 'close' not in self.state['completed']: raise RuntimeError('Cannot stop kernel until a verified normal close')
        self.collect()
        self.api('DELETE','kernels/'+self.state['kernel_id'])
        self.state['kernel_stopped_utc']=datetime.now(timezone.utc).isoformat();self.persist()
        self.log('FINISHED; only this run kernel stopped, files retained')


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['setup','collect','finish']+STAGES)
    p.add_argument('--config',choices=list(RELEASES),required=True)
    p.add_argument('--board',type=int,choices=[1,2,3],required=True)
    p.add_argument('--reservation-end',required=True,help='ISO 8601 with UTC offset, e.g. 2026-11-18T16:00:00-07:00')
    p.add_argument('--run-id',required=True,help='Unique folder label; re-use it for later stages of this run')
    a=p.parse_args()
    r=Run(a.config,a.board,datetime.fromisoformat(a.reservation_end),a.run_id)
    if a.action in STAGES:r.stage(a.action)
    else:getattr(r,a.action)()

if __name__=='__main__':main()
