import assert from 'node:assert/strict';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { repairCsdnHtml } from './repair_html.mjs';

const url=n=>'https://i-blog.csdnimg.cn/direct/test-'+n+'.png';
const images=n=>Array.from({length:n},(_,i)=>({order:i+1,caption:'图｜独立工作流程 '+(i+1)+'（来源说明）'}));
const urls=n=>Object.fromEntries(Array.from({length:n},(_,i)=>[i+1,url(i+1)]));
const body=n=>'<h1>原有标题</h1><p>正文 <a href="https://example.org/docs?a=1&amp;b=2">链接</a></p>'+Array.from({length:n},(_,i)=>'<p><span class="cke_widget_wrapper cke_widget_image" data-cke-widget-wrapper="1"><img src="file:///temporary.png"><span class="cke_widget_drag_handler_container"><img src="data:image/gif;base64,AA=="></span><span role="button" contenteditable="false" class="edit">编辑</span></span></p><p>图｜独立工作流程 '+(i+1)+'</p>').join('')+'<pre><code>first\nsecond &lt;value&gt;\n</code></pre><p>结尾不能丢。</p>';
let checks=0;
function test(name, fn) {fn();checks++;console.log('PASS '+name);}

for(const n of [1,2,17,29,31])test('arbitrary occurrence count '+n,()=>{
  const r=repairCsdnHtml(body(n),images(n),urls(n));
  assert.equal(r.audit.insertedImages,n);
  assert.equal((r.html.match(/<img /g)||[]).length,n);
  assert.equal(r.html.includes('file:///'),false);
  assert.equal(r.html.includes('编辑'),false);
  assert.ok(r.html.includes('<h1>原有标题</h1>'));
  assert.ok(r.html.includes('<pre><code>first\nsecond &lt;value&gt;\n</code></pre>'));
  assert.ok(r.html.includes('href="https://example.org/docs?a=1&amp;b=2"'));
  assert.ok(r.html.endsWith('<p>结尾不能丢。</p>'));
  assert.equal(repairCsdnHtml(r.html,images(n),urls(n)).html,r.html);
});
test('explicit cover and table caption',()=>{
  const r=repairCsdnHtml('<p>唯一副标题</p><table><tr><td><p>图｜表格内容图</p></td></tr></table>',[{order:1,caption:null},{order:2,caption:'图｜表格内容图'}],urls(2),{anchors:{1:{text:'唯一副标题',position:'after'}}});
  assert.ok(r.html.indexOf(url(1))<r.html.indexOf('<table>'));
  assert.equal(r.audit.images[1].position,'before');
});
test('repeated source with shared explicit position',()=>{
  const r=repairCsdnHtml('<p>共同上下文</p>',[{order:1},{order:2}],{1:url(1),2:url(1)},{anchors:{1:{text:'共同上下文',position:'after'},2:{text:'共同上下文',position:'after',allow_shared_anchor:true}}});
  assert.equal(r.audit.insertedImages,2);
});
test('refuse duplicate caption',()=>assert.throws(()=>repairCsdnHtml(body(1)+'<p>图｜独立工作流程 1</p>',images(1),urls(1)),/uniquely/));
test('refuse missing caption',()=>assert.throws(()=>repairCsdnHtml('<p>无标题</p>',[{order:1}],urls(1)),/explicit anchor/));
test('refuse missing URL',()=>assert.throws(()=>repairCsdnHtml(body(2),images(2),urls(1)),/URL/));
test('refuse placeholder masquerading as loaded image',()=>assert.throws(()=>repairCsdnHtml(body(1),images(1),{1:'https://i-blog.csdnimg.cn/images/20230724024159.png?origin_url=file%3Atemp'}),/placeholder/));
test('refuse unapproved or credentialled host',()=>{
  assert.throws(()=>repairCsdnHtml(body(1),images(1),{1:'https://example.org/image.png'}),/host/);
  assert.throws(()=>repairCsdnHtml(body(1),images(1),{1:'https://someone:secret@i-blog.csdnimg.cn/image.png'}),/host/);
});
test('refuse order conflict',()=>assert.throws(()=>repairCsdnHtml('<p>图｜独立工作流程 2</p><p>图｜独立工作流程 1</p>',images(2),urls(2)),/not in Word order/));
test('shortened unique caption',()=>{
  const r=repairCsdnHtml('<p>图｜这是足够独特的锚点标题</p>',[{order:1,caption:'图｜这是足够独特的锚点标题：扩展说明'}],urls(1));
  assert.equal(r.audit.images[0].match,'caption-prefix');
});

const work=await mkdtemp(join(tmpdir(),'csdn-skill-test-'));
try {
  await writeFile(join(work,'original.html'),body(2));
  await writeFile(join(work,'manifest.json'),JSON.stringify({images:images(2)}));
  await writeFile(join(work,'urls.json'),JSON.stringify(urls(2)));
  const cli=fileURLToPath(new URL('./repair_html.mjs',import.meta.url));
  const args=[cli,'--input',join(work,'original.html'),'--manifest',join(work,'manifest.json'),'--urls',join(work,'urls.json'),'--output',join(work,'fixed.html')];
  let p=spawnSync(process.execPath,args,{encoding:'utf8'});
  assert.equal(p.status,0,p.stderr);
  const before=await readFile(join(work,'fixed.html'),'utf8');
  p=spawnSync(process.execPath,args,{encoding:'utf8'});
  assert.notEqual(p.status,0);
  assert.match(p.stderr,/Refusing to overwrite/);
  assert.equal(await readFile(join(work,'fixed.html'),'utf8'),before);
  checks++;console.log('PASS CLI creates output and refuses overwrite');
} finally {
  await rm(work,{recursive:true,force:true});
}
console.log('All '+checks+' checks passed. No network or browser calls.');
