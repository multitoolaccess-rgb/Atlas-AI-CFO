import importlib.util, json, types
from pathlib import Path
import pytest
P=Path(__file__).parents[1]/'scripts/atlas_phase_operator.py'; spec=importlib.util.spec_from_file_location('op',P); op=importlib.util.module_from_spec(spec); spec.loader.exec_module(op)
def result(status='continue', handoff=True):
 return {'status':status,'summary':'done','completed_work':'x','validation':'x','git_state':'clean','tracker_state':'valid','next_bounded_task':'x','next_prompt':'next','handoff_updated':handoff}
def args(**kw): return types.SimpleNamespace(max_iterations=kw.get('max_iterations',2),max_elapsed=kw.get('max_elapsed',100),shutdown_margin=kw.get('shutdown_margin',10),sandbox='workspace-write',allow_dirty_dry_run=kw.get('allow_dirty_dry_run',False))
def state(**kw): return {'phase':'test','started':kw.get('started',0),'iterations':kw.get('iterations',0),'session_id':kw.get('session_id'),'crashed':False}
def fake(monkeypatch, output, rc=0, clean=True):
 monkeypatch.setattr(op,'safe_git',lambda: clean); monkeypatch.setattr(op,'save',lambda *x:None); monkeypatch.setattr(op.time,'time',lambda:50)
 seen=[]
 def run(cmd,**k): seen.append(cmd); return types.SimpleNamespace(stdout=output,stderr='',returncode=rc)
 monkeypatch.setattr(op.subprocess,'run',run); return seen
def jsonl(r, sid='exact-id'): return json.dumps({'thread_id':sid})+'\n'+json.dumps(r)
def test_exact_initial_and_resume_commands(monkeypatch,tmp_path):
 monkeypatch.setattr(op,'REPO',tmp_path); seen=fake(monkeypatch,jsonl(result())); op.run('test',state(),args()); assert seen[0][:2]==['codex','exec'] and '--last' not in seen[0] and '--ephemeral' not in seen[0] and '--output-schema' in seen[0]
 seen=fake(monkeypatch,jsonl(result())); op.run('test',state(session_id='exact-id'),args()); assert seen[0][:4]==['codex','exec','resume','exact-id'] and '--last' not in seen[0]
def test_every_terminal_status_stops(monkeypatch,tmp_path):
 monkeypatch.setattr(op,'REPO',tmp_path)
 for status in op.STATUSES:
  fake(monkeypatch,jsonl(result(status))); s=op.run('test',state(),args()); assert (s['stop'] is None) == (status=='continue')
def test_limits_only_between_iterations(monkeypatch,tmp_path):
 monkeypatch.setattr(op,'REPO',tmp_path); seen=fake(monkeypatch,''); s=op.run('test',state(iterations=2),args()); assert s['stop']=='budget_stop' and not seen
 seen=fake(monkeypatch,''); s=op.run('test',state(started=-100),args(max_elapsed=100,shutdown_margin=10)); assert s['stop']=='budget_stop' and not seen
def test_crash_jsonl_quota_and_state(monkeypatch,tmp_path):
 monkeypatch.setattr(op,'REPO',tmp_path)
 for out,rc in [('',1),('truncated',0),('rate limit',1)]:
  fake(monkeypatch,out,rc); s=op.run('test',state(),args()); assert s['crashed'] and s['stop']=='blocked_external'
def test_dirty_and_handoff_safety(monkeypatch,tmp_path):
 monkeypatch.setattr(op,'REPO',tmp_path); fake(monkeypatch,jsonl(result()),clean=False); assert op.run('test',state(),args())['stop']=='unsafe_state'
 fake(monkeypatch,jsonl(result(handoff=False))); assert op.run('test',state(),args())['stop']=='unsafe_state'
def test_merge_guard_and_sensitive_redaction():
 assert not op.merge_allowed('old','new',{'ci':'success'})
 assert not op.merge_allowed('new','new',{'ci':'pending'})
 assert op.merge_allowed('new','new',{'cheap':'success','heavy':'skipped'},('heavy',))
 assert '[REDACTED]' in op.redact('token=SYNTHETIC_SECRET_MARKER')
def test_persist_restore(monkeypatch,tmp_path):
 monkeypatch.setattr(op,'REPO',tmp_path); s=state(session_id='exact-id'); s['iterations']=1; op.save('test',s); assert op.load('test')['session_id']=='exact-id'
