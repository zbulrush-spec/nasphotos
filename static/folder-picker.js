/* Directory management lives in the library settings page. */
function setupLibraryPicker({api,onSaved}) {
  const get=id=>document.getElementById(id);
  const dialog=get('config'), chosen=new Set();
  let current='',busy=false;
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n};
  const error=message=>{get('folderError').textContent=message;get('folderError').hidden=!message};
  function selection(){
    get('selectedFolders').replaceChildren();
    for(const path of chosen){const row=node('div'),label=node('span',path),remove=node('button','移除');
      remove.type='button';remove.disabled=busy;remove.onclick=()=>{chosen.delete(path);selection();syncChecks()};row.append(label,remove);get('selectedFolders').append(row)}
    get('selectionCount').textContent=`已选择 ${chosen.size} 个目录（包含所有子目录）`;
    get('saveFolder').disabled=busy||chosen.size===0;
  }
  function syncChecks(){dialog.querySelectorAll('input[data-path]').forEach(input=>{input.checked=chosen.has(input.dataset.path);input.disabled=busy})}
  function checkbox(path,label){const wrap=node('label'),input=node('input');input.type='checkbox';input.dataset.path=path;input.checked=chosen.has(path);input.disabled=busy;
    input.onchange=()=>{if(input.checked)chosen.add(path);else chosen.delete(path);selection();syncChecks()};wrap.append(input,node('span',label));return wrap}
  async function browse(path){
    error('');get('folders').textContent='正在读取目录…';
    try{const d=await api('/api/folders?path='+encodeURIComponent(path));current=d.path;get('folderPath').textContent=current;
      get('currentFolder').replaceChildren(checkbox(current,'选择当前目录（包含这里的照片及所有子目录）'));
      const list=get('folders');list.replaceChildren();
      if(d.parent){const up=node('button','↑ 上一级');up.type='button';up.onclick=()=>browse(d.parent);list.append(up)}
      for(const child of d.folders){const row=node('div');row.className='folder-row';const open=node('button','打开 ›');open.type='button';open.onclick=()=>browse(child.path);row.append(checkbox(child.path,child.name),open);list.append(row)}
      get('folderHint').textContent=d.folders.length?`当前目录直接包含 ${d.media_count} 个图片或视频，可勾选多个文件夹。`:(d.media_count?`没有子文件夹，这里直接存放了 ${d.media_count} 个图片或视频。请勾选“选择当前目录”。`:'这个目录没有子文件夹，也没有图片或视频。若你的 NAS 有照片，请检查 Docker 文件夹映射是否指向了正确的照片目录。');
    }catch(e){get('folders').replaceChildren();get('currentFolder').replaceChildren();error(e.message)}
  }
  async function open(){
    if(busy)return;
    error('');get('saveFolder').disabled=true;
    try{
      const [lib,available]=await Promise.all([api('/api/library'),api('/api/roots')]);
      chosen.clear();lib.paths.forEach(path=>chosen.add(path));selection();get('folderRoots').replaceChildren();
      for(const root of available.roots){const b=node('button',root.path);b.type='button';b.onclick=()=>browse(root.path);get('folderRoots').append(b)}
      await browse(lib.paths[0]||(available.roots.find(root=>root.mounted)||available.roots[0]).path);
    }catch(e){error(e.message)}
  }
  get('saveFolder').onclick=async()=>{
    if(busy||!chosen.size)return;
    busy=true;error('');selection();syncChecks();get('saveFolder').textContent='正在保存…';
    try{
      await api('/api/library','POST',{paths:[...chosen]});
      await onSaved();
    }catch(e){error(e.message)}
    finally{busy=false;selection();syncChecks();get('saveFolder').textContent='保存所选目录'}
  };
  return {open};
}
