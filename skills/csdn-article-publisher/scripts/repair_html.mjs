/**
 * Reposition Word images without reserializing unrelated CSDN article HTML.
 * Usage: const { html, audit } = repairCsdnHtml(editorHtml, imgOrder, hostedMap, options);
 * imgOrder: [{order: 1, caption: '...', ...}, ...]
 * hostedMap: Map<number,string> or plain object {1: 'https://...', ...}.
 * Core function has no I/O. CLI reads/writes local files; never calls a website.
 */
const VOID = new Set('area base br col embed hr img input link meta param source track wbr'.split(' '));
const EDITOR_CLASS = /(?:^|\s)(?:cke_widget_drag_handler(?:_container)?|cke_widget_mask|cke_image_resizer(?:_wrapper)?|cke_widget_button|cke_image_button)(?:\s|$)/i;

function decodeEntities(s) {
  const named = {amp:'&',lt:'<',gt:'>',quot:'"',apos:"'",nbsp:' ',ensp:' ',emsp:' ',thinsp:' ',zwnj:'',zwj:'',ZeroWidthSpace:'',colon:':',vert:'|',VerticalLine:'|'};
  return s.replace(/&(#x[0-9a-f]+|#\d+|[a-zA-Z]+);/g, (all,key) => {
    if (key.startsWith('#')) {
      const n = key[1].toLowerCase()==='x' ? parseInt(key.slice(2),16) : parseInt(key.slice(1),10);
      return n>=0 && n<=0x10ffff ? String.fromCodePoint(n) : all;
    }
    return named[key] ?? all;
  });
}

function attributes(raw) {
  const result = Object.create(null);
  const content = raw.replace(/^<\s*[^\s/>]+/,'').replace(/\/?\s*>$/,'');
  const rx = /([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g;
  for (let m; (m=rx.exec(content));) result[m[1].toLowerCase()] = decodeEntities(m[2] ?? m[3] ?? m[4] ?? '');
  return result;
}

function parseHtml(source) {
  const root = {type:'root',children:[]};
  const stack = [root];
  let pos=0;
  const add = node => { node.parent=stack.at(-1); node.parent.children.push(node); };
  while (pos<source.length) {
    if (source.startsWith('<!--',pos)) {
      const end=source.indexOf('-->',pos+4), stop=end<0?source.length:end+3;
      add({type:'raw',raw:source.slice(pos,stop)});pos=stop;continue;
    }
    if (source[pos]!=='<' || !/^<(?:[a-zA-Z!/?])/.test(source.slice(pos,pos+2))) {
      let end=source.indexOf('<',pos+1); if(end<0)end=source.length;
      add({type:'text',raw:source.slice(pos,end)});pos=end;continue;
    }
    let end=pos+1,quote=null;
    for(;end<source.length;end++) {
      const c=source[end];
      if(quote) {if(c===quote)quote=null;}
      else if(c==='"'||c==="'")quote=c;
      else if(c==='>')break;
    }
    if(end===source.length)throw new Error('Malformed HTML: unterminated tag at '+pos);
    const raw=source.slice(pos,end+1);pos=end+1;
    const close=raw.match(/^<\/\s*([\w:-]+)/);
    if(close) {
      const name=close[1].toLowerCase();
      let found=-1;
      for(let i=stack.length-1;i>0;i--)if(stack[i].name===name){found=i;break;}
      if(found<0) {add({type:'raw',raw});continue;}
      // Preserve original end tags exactly. No normalization of original markup.
      stack[found].closeRaw=raw;stack.length=found;continue;
    }
    const open=raw.match(/^<\s*([a-zA-Z][\w:-]*)/);
    if(!open){add({type:'raw',raw});continue;}
    const name=open[1].toLowerCase();
    const node={type:'element',name,attrs:attributes(raw),openRaw:raw,closeRaw:'',children:[]};
    add(node);
    if(VOID.has(name)||/\/\s*>$/.test(raw))continue;
    if(name==='script'||name==='style') {
      const rx=new RegExp('</\\s*'+name+'\\s*>','ig');rx.lastIndex=pos;
      const m=rx.exec(source);
      if(!m)throw new Error('Malformed HTML: unclosed '+name);
      node.children.push({type:'raw',raw:source.slice(pos,m.index),parent:node});
      node.closeRaw=m[0];pos=rx.lastIndex;continue;
    }
    stack.push(node);
  }
  return root;
}

function walk(node,fn) {fn(node);for(const child of node.children??[])walk(child,fn);}
function hasImage(node) {
  if(node.type==='element'&&node.name==='img')return true;
  return (node.children??[]).some(hasImage);
}
function visibleText(node) {
  if(node.type==='text')return decodeEntities(node.raw);
  if(node.type!=='root'&&node.type!=='element')return '';
  if(node.name==='script'||node.name==='style'||node.name==='img')return '';
  if(node.name==='br')return '\n';
  return (node.children??[]).map(visibleText).join('');
}
function normalize(s) {return decodeEntities(s).normalize('NFKC').replace(/[\s\u200b\ufeff]+/g,'').replace(/[：]/g,':');}
function captionBase(s) {
  let value=decodeEntities(s).normalize('NFKC').trim();
  if(!/^图\s*[|｜:：]/.test(value))return null;
  value=value.replace(/^图\s*[|｜:：]\s*/,'').split(/[（(]/,1)[0].trim();
  return normalize(value).replace(/[。；;]+$/,'');
}
function escAttr(s){return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');}

function cleanTree(root,stats) {
  function cleanup(node,inImageWidget=false) {
    if(node.type!=='element'&&node.type!=='root')return [node];
    if(node.name==='img') {stats.removedImages++;return [];}
    const a=node.attrs??{};
    const imageWidget=node.type==='element' && hasImage(node) &&
      (/(?:^|\s)cke_widget_wrapper(?:\s|$)/.test(a.class??'') || 'data-cke-widget-wrapper' in a);
    const inside=inImageWidget||imageWidget;
    const txt=normalize(visibleText(node));
    const editorControl=node.type==='element' && !imageWidget && (
      EDITOR_CLASS.test(a.class??'') ||
      (inside && ['button','a','span'].includes(node.name) &&
        /^(编辑|删除|拖动|拖拽|调整大小|Edit|Delete|Resize)$/i.test(txt) &&
        (node.name==='button'||a.role==='button'||a.contenteditable==='false'||/cke_|edit|delete|resize|drag/i.test((a.class??'')+' '+(a.title??''))))
    );
    if(editorControl){
      stats.removedEditorControls++;
      walk(node,n=>{if(n.type==='element'&&n.name==='img')stats.removedImages++;});
      return [];
    }
    const originallyHadImage=hasImage(node);
    node.children=(node.children??[]).flatMap(child=>cleanup(child,inside));
    for(const child of node.children)child.parent=node;
    if(imageWidget) {
      stats.unwrappedImageWidgets++;
      // Any real caption/prose inside an image widget survives the unwrap.
      return node.children;
    }
    // Remove only paragraphs made empty by removing original pictures.
    if(node.name==='p'&&originallyHadImage&&!normalize(visibleText(node))&&!hasImage(node)) {
      stats.removedEmptyImageParagraphs++;return [];
    }
    return [node];
  }
  root.children=root.children.flatMap(child=>cleanup(child));
  for(const child of root.children)child.parent=root;
}

function render(node) {
  if(node.type==='raw'||node.type==='text')return node.raw;
  const inside=(node.children??[]).map(render).join('');
  return (node.before??'')+(node.type==='root'?inside:node.openRaw+inside+node.closeRaw)+(node.after??'');
}

/** Return {html, audit}; throws before returning if any location is ambiguous. */
export function repairCsdnHtml(editorHtml,imgOrder,hostedMap,options={}) {
  if(typeof editorHtml!=='string'||!editorHtml.trim())throw new Error('editorHtml must be a nonempty string');
  if(!Array.isArray(imgOrder)||!imgOrder.length)throw new Error('Expected a nonempty Word image inventory');
  const ordered=[...imgOrder].sort((a,b)=>Number(a.order)-Number(b.order));
  if(ordered.some((r,i)=>Number(r.order)!==i+1))throw new Error('Image order must contain each integer 1..N once');
  const urlFor = order => hostedMap instanceof Map ? hostedMap.get(order)??hostedMap.get(String(order)) : hostedMap?.[order];
  const urls=ordered.map(r=>urlFor(Number(r.order)));
  for(let i=0;i<urls.length;i++) {
    if(typeof urls[i]!=='string'||!/^https:\/\/[^\s<>"']+$/.test(urls[i]))throw new Error('Missing or invalid hosted HTTPS URL for image '+(i+1));
    const u=new URL(urls[i]);
    const hosts=options.allowedHosts??['i-blog.csdnimg.cn','img-blog.csdnimg.cn'];
    if(u.username||u.password||!hosts.includes(u.hostname))throw new Error('Unapproved image host for image '+(i+1));
    if(/(?:file%3a|file:|\/20230724024159\.png)/i.test(urls[i]))throw new Error('Broken/local image placeholder for image '+(i+1));
  }
  const root=parseHtml(editorHtml);
  const stats={removedImages:0,unwrappedImageWidgets:0,removedEditorControls:0,removedEmptyImageParagraphs:0};
  cleanTree(root,stats);
  const paragraphs=[];
  walk(root,node=>{if(node.type==='element'&&node.name==='p')paragraphs.push(node);});
  const candidates=paragraphs.map((p,paragraphIndex)=>({node:p,paragraphIndex,text:visibleText(p).trim(),base:captionBase(visibleText(p))})).filter(x=>x.base);
  const anchors=[];
  const used=new Set();
  for(const record of ordered) {
    const override=options.anchors?.[record.order];
    if(override) {
      if(!override.text||!['before','after'].includes(override.position))throw new Error('Invalid explicit anchor for image '+record.order);
      const found=paragraphs.map((node,paragraphIndex)=>({node,paragraphIndex})).filter(x=>normalize(visibleText(x.node))===normalize(override.text)&&(override.paragraph_index===undefined||x.paragraphIndex===override.paragraph_index));
      if(found.length!==1)throw new Error('Explicit anchor must match uniquely for image '+record.order+'; found '+found.length);
      const match=found[0],key=match.paragraphIndex+':'+override.position;
      if(used.has(key)&&!override.allow_shared_anchor)throw new Error('Shared explicit anchor needs allow_shared_anchor: true for image '+record.order);
      used.add(key);
      anchors.push({order:Number(record.order),...match,position:override.position,anchorText:visibleText(match.node).trim(),match:'explicit'});
      continue;
    }
    const expected=captionBase(record.caption??'');
    if(!expected)throw new Error('No usable caption for image '+record.order+'; supply a verified explicit anchor');
    const head=expected.split(':',1)[0];
    let matchMode='caption-exact';
    let matches=candidates.filter(c=>c.base===expected);
    if(matches.length===0) {
      matchMode='caption-prefix';
      matches=candidates.filter(c=>(c.base.startsWith(expected)||expected.startsWith(c.base)) && Math.min(c.base.length,expected.length)>=8);
    }
    if(matches.length===0 && head.length>=4) {
      // Last fallback: the actual caption retains the distinctive title before ':'
      // but abbreviates the explanatory suffix. Still require exactly one match.
      matchMode='caption-title-prefix';
      matches=candidates.filter(c=>c.base===head||c.base.startsWith(head+':'));
    }
    if(matches.length!==1)throw new Error('Image '+record.order+' caption must match uniquely; found '+matches.length+' for '+record.caption);
    const match=matches[0];
    const key=match.paragraphIndex+':before';
    if(used.has(key))throw new Error('Caption reused by two images: '+match.text);
    used.add(key);
    anchors.push({order:Number(record.order),node:match.node,position:'before',paragraphIndex:match.paragraphIndex,anchorText:match.text,expectedCaption:record.caption,match:matchMode});
  }
  const rank=a=>a.paragraphIndex*2+(a.position==='after'?1:0);
  if(anchors.some((a,i)=>i>0&&rank(a)<rank(anchors[i-1])))throw new Error('Matched image anchors are not in Word order; refusing to guess');
  for(const anchor of anchors) {
    const record=ordered[anchor.order-1],url=urls[anchor.order-1];
    const image='<p style="text-align:center;">'+
      '<img src="'+escAttr(url)+'" alt="'+escAttr(record.caption??('图片 '+anchor.order))+'" data-word-image="'+String(anchor.order).padStart(2,'0')+'" style="display:block;max-width:100%;height:auto;margin:0 auto;" />'+
      '</p>';
    anchor.node[anchor.position]=(anchor.node[anchor.position]??'')+image;
  }
  const html=render(root);
  const finalRoot=parseHtml(html), finalImages=[];
  walk(finalRoot,n=>{if(n.type==='element'&&n.name==='img')finalImages.push(n);});
  if(finalImages.length!==ordered.length||finalImages.some((n,i)=>n.attrs.src!==urls[i]))throw new Error('Final image-count or order audit failed');
  return {html,audit:{...stats,insertedImages:ordered.length,allAnchorsResolved:true,allImagesInWordOrder:true,images:anchors.map(({node,...a})=>({...a,url:urls[a.order-1]}))}};
}

export default repairCsdnHtml;

// CLI is intentionally separate from browser control and publication.
import { readFile, writeFile, access } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
async function main(args) {
  if(args.includes('--help')||!args.length) {
    console.log('node repair_html.mjs --input original-body.html --manifest manifest.json --urls hosted-map.json --output repaired.html [--anchors anchors.json] [--audit audit.json] [--allow-host hostname]');
    return;
  }
  const opt={};
  for(let i=0;i<args.length;i+=2) {
    const k=args[i],v=args[i+1];
    if(!['--input','--manifest','--urls','--output','--anchors','--audit','--allow-host'].includes(k)||!v||v.startsWith('--'))throw new Error('Invalid argument '+k);
    if(k==='--allow-host')(opt.allowedHosts??=['i-blog.csdnimg.cn','img-blog.csdnimg.cn']).push(v);
    else opt[k.slice(2)]=v;
  }
  for(const k of ['input','manifest','urls','output'])if(!opt[k])throw new Error('Missing --'+k);
  const output=resolve(opt.output),auditPath=resolve(opt.audit??opt.output+'.audit.json');
  if(output===auditPath)throw new Error('Output and audit must be different paths');
  for(const p of [output,auditPath]) {
    try {await access(p);} catch(e) {if(e.code==='ENOENT')continue;throw e;}
    throw new Error('Refusing to overwrite existing file: '+p);
  }
  const manifest=JSON.parse(await readFile(opt.manifest,'utf8'));
  const images=Array.isArray(manifest)?manifest:manifest.images;
  const result=repairCsdnHtml(await readFile(opt.input,'utf8'),images,JSON.parse(await readFile(opt.urls,'utf8')),{anchors:opt.anchors?JSON.parse(await readFile(opt.anchors,'utf8')):{},allowedHosts:opt.allowedHosts});
  await writeFile(output,result.html,{flag:'wx'});
  await writeFile(auditPath,JSON.stringify(result.audit,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({output,audit:auditPath,images:result.audit.insertedImages}));
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)main(process.argv.slice(2)).catch(e=>{console.error(e.message);process.exitCode=1;});
