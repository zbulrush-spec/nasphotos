const $ = s => document.querySelector(s);
const titles = {all:'所有照片',video:'视频',places:'地点',people:'人物',shares:'分享管理',trash:'最近删除',settings:'图库设置'};
let view='all',items=[],offset=0,total=0,selected=null,poll=null,loading=false,hasMore=false,loadVersion=0;
let region=null,person=null,map=null,mapMarkers=null,mapVersion=0,viewerVersion=0,dismissedScan=null,wasRunning=false;
let videoCleanup=()=>{};
function toast(s){$('#toast').textContent=s;$('#toast').style.display='block';clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').style.display='none',3500)}
async function api(url,method='GET',body){const r=await fetch(url,{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});let data;try{data=await r.json()}catch{throw Error('操作失败，请检查文件权限或服务器日志')}if(!r.ok)throw Error(data.error||'操作失败');return data}
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n}
async function start(){const s=await api('/api/status');$('#login').hidden=s.authenticated;$('#app').hidden=!s.authenticated;$('#loginHint').textContent=s.setup?'输入密码，回到你的时光。':'首次使用，请设置至少12位的管理员密码。';if(s.authenticated){clearInterval(poll);poll=setInterval(()=>{checkScan();checkRecognition()},2000);await checkScan();const lib=await api('/api/library');await navigate(lib.paths.length?'all':'settings')}}
$('#loginForm').onsubmit=async e=>{e.preventDefault();try{await api('/api/login','POST',{password:$('#password').value});$('#password').value='';await start()}catch(e){$('#loginError').textContent=e.message}};
$('#logout').onclick=async()=>{await api('/api/logout','POST',{});clearInterval(poll);location.reload()};
document.querySelectorAll('.nav[data-view]').forEach(b=>b.onclick=()=>navigate(b.dataset.view).catch(e=>toast(e.message)));
async function navigate(next){view=next;region=null;person=null;document.querySelectorAll('.nav').forEach(b=>b.classList.toggle('active',b.dataset.view===view));$('#title').textContent=titles[view];$('#config').hidden=view!=='settings';$('#placesPanel').hidden=view!=='places';$('#personPanel').hidden=true;$('#clearRegion').hidden=true;await load();if(view==='settings'){await picker.open();await checkRecognition();await loadRecognitionKey()}if(view==='places')await showMap()}
function mediaParams(){const p=new URLSearchParams({trash:view==='trash'?'1':'0',offset:String(offset)});if(view==='video')p.set('kind','video');if(region)p.set('bounds',region.join(','));if(person)p.set('person',person.id);return p}
function paginated(){return ['all','video','trash'].includes(view)||(view==='places'&&region)||(view==='people'&&person)}
async function load(more=false){
  if(more&&(loading||!hasMore))return;
  const version=more?loadVersion:++loadVersion;
  if(!more){items=[];offset=0;total=0;hasMore=false;$('#gallery').replaceChildren();$('#retryLoad').hidden=true}
  loading=true;$('#loadSentinel').hidden=!paginated();$('#loadSentinel').textContent='正在加载…';
  try{
    if(view==='settings'){$('#count').textContent='管理照片目录、扫描和本地人脸识别';return}
    if(view==='places'&&!region){$('#count').textContent='在地图上探索照片';return}
    if(view==='people'&&!person){await loadPeople(version);return}
    if(view==='shares'){const rows=await api('/api/shares');if(version!==loadVersion)return;for(const r of rows){const n=el('div',undefined,'share-row'),a=el('a','打开分享');a.href='/s/'+r.token;a.target='_blank';a.rel='noreferrer';n.append(a,el('span',new Date(r.expires*1000).toLocaleDateString()+' 到期'));const b=el('button','撤销');b.onclick=async()=>{try{await api('/api/shares/'+r.token,'DELETE');await load()}catch(e){toast(e.message)}};n.append(b);$('#gallery').append(n)}$('#count').textContent=rows.length+' 个分享链接';return}
    const data=await api('/api/media?'+mediaParams());if(version!==loadVersion)return;
    items.push(...data.items);offset+=data.items.length;total=data.total;hasMore=offset<total&&data.items.length>0;appendMedia(data.items);
    $('#count').textContent=total+' 个项目'+(view==='trash'?' · 按删除日期排列，30天后永久清除':'');
    if(!items.length){const n=el('div',undefined,'empty');n.append(el('div','✺'),el('strong',view==='trash'?'回收站是空的':'暂无照片'),el('p','可在图库设置中选择目录并扫描。'));$('#gallery').append(n)}
  }catch(e){if(version===loadVersion){hasMore=false;$('#retryLoad').hidden=false;toast(e.message)}}
  finally{if(version===loadVersion){loading=false;$('#loadSentinel').hidden=!hasMore;$('#loadSentinel').textContent=hasMore?'继续下拉加载照片':'';if(hasMore)requestAnimationFrame(maybeLoadMore)}}
}
function appendMedia(rows){let grid=$('#gallery .grid:last-child'),last=grid?.dataset.day;for(const r of rows){const day=view==='trash'?new Date(r.deleted*1000).toLocaleDateString('zh-CN'):r.date.slice(0,10);if(day!==last){last=day;$('#gallery').append(el('h2',(view==='trash'?'删除于 ':'')+day));grid=el('div',undefined,'grid');grid.dataset.day=day;$('#gallery').append(grid)}const b=el('button',undefined,'tile'),img=el('img');b.setAttribute('aria-label','查看 '+r.path.split('/').pop());img.src='/api/media/'+r.id+'/thumb';img.loading='lazy';img.alt=r.path.split('/').pop();b.onclick=()=>open(r);b.append(img);if(r.kind==='video')b.append(el('span','▶'));grid.append(b)}}
function maybeLoadMore(){if(hasMore&&!loading&&!$('#app').hidden&&$('#loadSentinel').getBoundingClientRect().top<innerHeight+800)load(true)}
new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting))maybeLoadMore()},{rootMargin:'800px'}).observe($('#loadSentinel'));
window.addEventListener('scroll',maybeLoadMore,{passive:true});$('#retryLoad').onclick=()=>load();

async function showMap(){
  if(typeof L==='undefined'){$('#notice').textContent='地图组件加载失败，请刷新页面重试。';return}
  if(!map){map=L.map('map',{maxZoom:19}).setView([30,105],3);L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}).addTo(map);mapMarkers=L.layerGroup().addTo(map);map.on('moveend',()=>refreshMap().catch(e=>toast(e.message)))}
  map.invalidateSize();await refreshMap(true);
}
async function refreshMap(fit=false){
  if(view!=='places')return;const version=++mapVersion;
  const params=new URLSearchParams({zoom:String(fit?0:map.getZoom())});const bounds=map.getBounds();if(!fit&&bounds.getEast()-bounds.getWest()<360)params.set('bounds',[Math.max(-90,bounds.getSouth()),((bounds.getWest()+180)%360+360)%360-180,Math.min(90,bounds.getNorth()),((bounds.getEast()+180)%360+360)%360-180].join(','));const data=await api('/api/places?'+params);if(version!==mapVersion||view!=='places')return;if(fit&&data.bounds){map.fitBounds([[data.bounds[0],data.bounds[1]],[data.bounds[2],data.bounds[3]]],{padding:[65,65],maxZoom:12});return refreshMap()}
  mapMarkers.clearLayers();if(!region)$('#count').textContent=data.total+' 个包含地点的项目';
  for(const g of data.clusters){const content=el('div',undefined,'map-cluster'),img=el('img');img.src='/api/media/'+g.id+'/thumb';img.alt='';content.append(img,el('span',String(g.count)));const marker=L.marker([g.lat,g.lon],{icon:L.divIcon({html:content,className:'photo-marker',iconSize:[66,78],iconAnchor:[33,78]}),title:g.count+' 个项目',keyboard:true});marker.on('click',async()=>{try{if(g.leaf){region=g.bounds;$('#clearRegion').hidden=false;await load();$('#gallery').scrollIntoView({behavior:'smooth',block:'start'})}else{const previous=map.getZoom();const bounds=L.latLngBounds([[g.bounds[0],g.bounds[1]],[g.bounds[2],g.bounds[3]]]);const zoom=Math.min(18,Math.max(previous+1,Math.min(previous+3,map.getBoundsZoom(bounds,false,[110,110]))));map.setView(bounds.getCenter(),zoom)}}catch(e){toast(e.message)}});marker.addTo(mapMarkers)}
}
$('#clearRegion').onclick=async()=>{region=null;$('#clearRegion').hidden=true;await load();await refreshMap()};
async function loadPeople(version){const rows=await api('/api/people');if(version!==loadVersion)return;$('#count').textContent=rows.length+' 位人物';if(!rows.length){const n=el('div',undefined,'empty');n.append(el('strong','还没有识别人物'),el('p','在图库设置中点击“识别图库人物”，完成后即可按人物浏览照片。'));$('#gallery').append(n);return}const grid=el('div',undefined,'people-grid');for(const p of rows){const b=el('button',undefined,'person-card'),img=el('img');img.src='/api/faces/'+p.cover+'/thumb';img.loading='lazy';img.alt=p.name||'未命名人物';b.append(img,el('strong',p.name||'未命名人物'),el('span',p.count+' 张照片'));b.onclick=async()=>{person=p;$('#title').textContent=p.name||'未命名人物';$('#personPanel').hidden=false;await load()};grid.append(b)}$('#gallery').append(grid)}
$('#backPeople').onclick=()=>navigate('people');$('#renamePerson').onclick=async()=>{const name=prompt('输入人物名称',person.name||'');if(name===null)return;try{await api('/api/people/'+person.id,'PATCH',{name});person.name=name;$('#title').textContent=name||'未命名人物'}catch(e){toast(e.message)}};

function open(r){
  videoCleanup();const version=++viewerVersion;selected=r;$('#filename').textContent=r.path;$('#mediaView').replaceChildren();$('#download').href='/api/media/'+r.id+'/download';$('#details').hidden=true;$('#share').hidden=!!r.deleted;$('#delete').hidden=!!r.deleted;$('#restore').hidden=!r.deleted;
  const stage=el('div',undefined,'media-stage'),thumbPath='/api/media/'+r.id+'/thumb';const thumb=[...$('#gallery').querySelectorAll('.tile img')].find(img=>img.getAttribute('src')===thumbPath)||el('img');if(thumb.parentElement)thumb.replaceWith(thumb.cloneNode(true));if(!thumb.getAttribute('src'))thumb.src=thumbPath;thumb.alt=r.path;thumb.className='preview-placeholder';stage.append(thumb);$('#mediaView').append(stage);
  const indicator=el('div',undefined,'media-loading');indicator.setAttribute('role','status');indicator.append(el('span',undefined,'spinner'),el('span',r.kind==='video'?'正在加载视频…':'正在加载原图…'));stage.append(indicator);
  if(r.kind==='video'){
    const video=el('video');video.controls=true;video.preload='auto';video.poster=thumb.src;video.src='/api/media/'+r.id+'/original';video.hidden=true;stage.append(video);
    const bar=el('progress');bar.max=100;bar.setAttribute('aria-label','视频缓冲进度');const label=el('span','正在读取视频…');indicator.append(bar,label);
    function update(){if(viewerVersion!==version)return;const duration=video.duration;let end=0;for(let i=0;i<video.buffered.length;i++)end=Math.max(end,video.buffered.end(i));if(Number.isFinite(duration)&&duration>0){bar.value=Math.min(100,end/duration*100);label.textContent='已缓冲 '+Math.round(bar.value)+'%'}else{bar.removeAttribute('value');label.textContent='正在读取视频…'}}
    const ready=()=>{if(viewerVersion!==version)return;video.hidden=false;thumb.hidden=true;indicator.hidden=true;update()};
    video.addEventListener('progress',update);video.addEventListener('loadedmetadata',update);video.addEventListener('canplay',ready);video.addEventListener('playing',ready);video.addEventListener('waiting',()=>{indicator.hidden=false;update()});video.addEventListener('stalled',()=>{if(video.readyState<3)indicator.hidden=false});video.addEventListener('error',()=>{indicator.replaceChildren(el('span','视频加载失败或浏览器不支持此编码，可下载原文件查看。'));video.hidden=true;thumb.hidden=false});
    videoCleanup=()=>{video.pause();video.removeAttribute('src');video.load()};
  }else{
    const image=new Image();image.alt=r.path;
    image.onload=async()=>{try{await image.decode()}catch{}if(viewerVersion!==version)return;image.className='full-image';stage.replaceChildren(image)};
    image.onerror=()=>{if(viewerVersion===version)indicator.replaceChildren(el('span','原图加载失败，仍显示缩略图。可下载原文件查看。'))};
    image.src='/api/media/'+r.id+'/preview';videoCleanup=()=>{image.onload=null;image.onerror=null;image.src=''};
  }
  if(!$('#viewer').open)$('#viewer').showModal();
}
$('#closeViewer').onclick=()=>$('#viewer').close();$('#viewer').addEventListener('close',()=>{++viewerVersion;videoCleanup();videoCleanup=()=>{};$('#mediaView').replaceChildren()});
$('#info').onclick=()=>{$('#details').textContent=`${selected.path}\n拍摄/文件日期：${selected.date}\n${selected.deleted?'删除日期：'+new Date(selected.deleted*1000).toLocaleString()+'\n':''}尺寸：${selected.width} × ${selected.height}\n文件大小：${(selected.size/1024/1024).toFixed(2)} MB\nGPS：${selected.lat??'无'} / ${selected.lon??'无'}`;$('#details').hidden=!$('#details').hidden};
$('#delete').onclick=async()=>{if(!confirm('将原文件移入回收站？30天后将永久删除，可在此之前恢复。'))return;try{await api('/api/media/'+selected.id+'/trash','POST',{});$('#viewer').close();await load()}catch(e){toast(e.message)}};
$('#restore').onclick=async()=>{try{await api('/api/media/'+selected.id+'/restore','POST',{});$('#viewer').close();await load();toast('已恢复到原目录')}catch(e){toast(e.message)}};
$('#share').onclick=()=>{$('#shareResult').hidden=true;$('#shareDialog').showModal()};$('#closeShare').onclick=()=>$('#shareDialog').close();$('#shareForm').onsubmit=async e=>{e.preventDefault();try{const s=await api('/api/shares','POST',{id:selected.id,days:Number($('#days').value),password:$('#sharePassword').value,download:$('#allowDownload').checked});$('#shareResult').hidden=false;$('#shareResult').value=location.origin+s.url;$('#shareResult').select()}catch(e){toast(e.message)}};
const picker=setupLibraryPicker({api,onSaved:async()=>toast('图库目录已保存，可点击“扫描图库”更新照片')});
$('#scan').onclick=async()=>{try{await api('/api/scan','POST',{});dismissedScan=null;wasRunning=true;await checkScan()}catch(e){toast(e.message)}};
$('#dismissScan').onclick=()=>{dismissedScan=$('#progress').dataset.task;$('#progress').hidden=true};
async function checkScan(){try{const p=await api('/api/scan');const task=p.task_id||'initial';$('#progress').dataset.task=task;$('#progress').hidden=p.phase==='idle'||(!p.running&&dismissedScan===task);$('#dismissScan').hidden=p.running;$('#phase').textContent=({discovering:'正在发现文件',processing:'正在读取信息与生成缩略图',complete:'扫描完成',failed:'扫描失败'})[p.phase]||'准备扫描';$('#bar').value=p.discovered?p.processed/p.discovered*100:0;if(p.phase==='discovering')$('#bar').removeAttribute('value');$('#scanCount').textContent=`已发现 ${p.discovered} · 已处理 ${p.processed} · 失败 ${p.errors} ${p.message||''}`;$('#scan').disabled=p.running;if(wasRunning&&!p.running){if(view!=='settings')await load();if(view==='places')await refreshMap()}wasRunning=p.running}catch(e){$('#notice').textContent='无法读取扫描状态：'+e.message}}
let recognitionRunning=false;
$('#recognize').onclick=async()=>{try{await api('/api/recognition','POST',{});await checkRecognition()}catch(e){toast(e.message)}};
async function loadRecognitionKey(){try{const s=await api('/api/recognition/key');$('#recognitionKeyStatus').textContent=s.configured?'密钥已配置并保存在图库数据库中。留空保存不会更改密钥。':'尚未配置密钥。'}catch(e){$('#recognitionKeyStatus').textContent=e.message}}
$('#saveRecognitionKey').onclick=async()=>{const key=$('#recognitionKey').value;if(!key){toast('请输入新的识别服务密钥');return}try{await api('/api/recognition/key','PUT',{key});$('#recognitionKey').value='';await loadRecognitionKey();toast('识别服务密钥已保存')}catch(e){toast(e.message)}};
async function checkRecognition(){try{const p=await api('/api/recognition');$('#recognize').disabled=p.running;$('#recognitionStatus').textContent=({idle:'尚未运行识别',processing:'正在识别人物',complete:'识别完成',failed:'识别失败'})[p.phase]+` · 已处理 ${p.processed}/${p.total} · 失败 ${p.errors}`+(p.message?' · '+p.message:'');if(recognitionRunning&&!p.running&&view==='people')await load();recognitionRunning=p.running}catch(e){if(view==='settings')$('#recognitionStatus').textContent=e.message}}
start().catch(e=>toast(e.message));
