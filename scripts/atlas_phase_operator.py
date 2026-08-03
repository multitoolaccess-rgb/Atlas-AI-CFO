#!/usr/bin/env python3
"""Explicit, stateful Atlas phase operator; intentionally does not start itself."""
import argparse, json, subprocess, time, re
from pathlib import Path

REPO=Path('/Users/vijayuppala/Documents/Projects/Atlas-AI-CFO')
STATUSES={'continue','blocked_user','blocked_external','phase_complete','budget_stop','unsafe_state'}
FIELDS={'status','summary','completed_work','validation','git_state','tracker_state','next_bounded_task','next_prompt','handoff_updated'}
SCHEMA={'type':'object','required':sorted(FIELDS),'additionalProperties':False,'properties':{k:({'type':'boolean'} if k=='handoff_updated' else {'type':'string'}) for k in FIELDS}}

def state_path(phase): return REPO/'.atlas-operator-state'/f'{phase}.json'
def load(phase):
 p=state_path(phase); return json.loads(p.read_text()) if p.exists() else None
def save(phase, state):
 p=state_path(phase); p.parent.mkdir(exist_ok=True); p.write_text(json.dumps(state,indent=2)+'\n')
def safe_git():
 return not subprocess.check_output(['git','status','--porcelain'],cwd=REPO,text=True).strip()
def redact(text):
 """Never persist likely credentials or raw financial payload markers."""
 return re.sub(r'(?i)(token|secret|password|authorization|api[_-]?key|account_number|transaction_amount)\s*[:=]\s*[^\s,}]+',r'\1=[REDACTED]',str(text))
def merge_allowed(review_head, final_head, checks, allowed_skips=()):
 if review_head != final_head: return False
 for name, status in checks.items():
  if status == 'success': continue
  if status == 'skipped' and name in allowed_skips: continue
  return False
 return True
def validate(result):
 if not isinstance(result,dict) or set(result)!=FIELDS or result['status'] not in STATUSES: raise ValueError('malformed iteration result')
 if not all(isinstance(result[k],str) for k in FIELDS-{'handoff_updated'}): raise ValueError('result fields must be strings')
 if not isinstance(result['handoff_updated'],bool): raise ValueError('handoff_updated must be boolean')
 return result
def extract(lines):
 for line in reversed(lines):
  try: return validate(json.loads(line))
  except (json.JSONDecodeError,ValueError): pass
 raise ValueError('no schema-valid iteration result in JSONL')
def quota(text): return any(x in text.lower() for x in ('rate limit','quota','credit'))
def run(phase, state, args):
 if not safe_git() and not getattr(args,'allow_dirty_dry_run',False):
  state['stop']='unsafe_state'; save(phase,state); return state
 if state.get('iterations',0)>=args.max_iterations or time.time()-state['started']>=args.max_elapsed-args.shutdown_margin:
  state['stop']='budget_stop'; save(phase,state); return state
 prompt=state.get('next_prompt') or f'Operate {phase} under Atlas governance. Return only the required result JSON.'
 schema=state_path(phase).with_suffix('.schema.json'); schema.parent.mkdir(exist_ok=True); schema.write_text(json.dumps(SCHEMA))
 cmd=['codex','exec']
 if state.get('session_id'): cmd.extend(['resume',state['session_id'],prompt,'--json','--output-schema',str(schema)])
 else: cmd.extend(['--json','--sandbox',args.sandbox,'--output-schema',str(schema),prompt])
 out=subprocess.run(cmd,cwd=REPO,text=True,capture_output=True)
 lines=out.stdout.splitlines(); text=out.stdout+'\n'+out.stderr
 if out.returncode or quota(text): state.update(crashed=True,stop='blocked_external',error=redact(text)); save(phase,state); return state
 try: result=extract(lines)
 except ValueError as exc: state.update(crashed=True,stop='blocked_external',error=redact(exc)); save(phase,state); return state
 # Session id is accepted only from structured Codex event output.
 for line in lines:
  try:
   e=json.loads(line); sid=e.get('session_id') or e.get('thread_id') or e.get('thread',{}).get('id')
   if sid: state['session_id']=sid
  except json.JSONDecodeError: pass
 if not state.get('session_id'): raise RuntimeError('Codex JSONL did not provide a session id')
 if result['status']=='continue' and not result['handoff_updated']:
  state.update(crashed=False,stop='unsafe_state',error='handoff validation required'); save(phase,state); return state
 state.update(iterations=state.get('iterations',0)+1,next_prompt=redact(result['next_prompt']),last={k:(redact(v) if isinstance(v,str) else v) for k,v in result.items()},crashed=False)
 state['stop']=None if result['status']=='continue' else result['status']; save(phase,state); return state
def main():
 p=argparse.ArgumentParser(); p.add_argument('command',choices=['start','resume','dry-run']); p.add_argument('--phase',required=True); p.add_argument('--max-iterations',type=int,default=20); p.add_argument('--max-elapsed',type=int,default=14400); p.add_argument('--shutdown-margin',type=int,default=300); p.add_argument('--correction-cycle-limit',type=int,default=2); p.add_argument('--sandbox',default='workspace-write'); a=p.parse_args()
 s=load(a.phase)
 if a.command=='dry-run':
  print(json.dumps({'phase':a.phase,'safe_git':safe_git(),'persistent_files':str(state_path(a.phase)),'command':'codex exec --json --sandbox workspace-write (no --last, no bypass flags)'},indent=2)); return
 if a.command=='start':
  if s: raise SystemExit('saved operator state exists; use resume')
  s={'phase':a.phase,'started':time.time(),'iterations':0,'session_id':None,'crashed':False}
 elif not s: raise SystemExit('no saved operator state')
 if s.get('crashed') and not safe_git(): raise SystemExit('unsafe dirty-tree recovery: inspect Git, tracker, handoff, processes, and incomplete work read-only first')
 print(json.dumps(run(a.phase,s,a),indent=2))
if __name__=='__main__': main()
