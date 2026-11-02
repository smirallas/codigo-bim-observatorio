import * as maplibregl from './maplibre-gl.mjs';
import {inspector} from './inspector.js';
import {categories} from './categories.js';
import {weatherMaps} from './weather.js';
import {domains} from './domains.js';
const $=id=>document.getElementById(id);
const map=new maplibregl.Map({container:'map',locale:{'NavigationControl.ZoomIn':'Acercar','NavigationControl.ZoomOut':'Alejar','NavigationControl.ResetBearing':'Orientar al norte','FullscreenControl.Enter':'Pantalla completa','FullscreenControl.Exit':'Salir de pantalla completa'},style:{version:8,sources:{geography:{type:'geojson',data:'geography.json'}},layers:[{id:'background',type:'background',paint:{'background-color':'#dce8e9'}},{id:'land',type:'fill',source:'geography',paint:{'fill-color':'#e8ede4','fill-outline-color':'#b4c2b9'}}]},center:[-3.8,39.7],zoom:10,attributionControl:false});
map.addControl(new maplibregl.NavigationControl(),'top-right');
map.addControl(new maplibregl.FullscreenControl(),'top-right');
map.on('movestart',()=>{document.body.dataset.mapIdle='false';});
map.on('idle',()=>{document.body.dataset.mapIdle='true';});
let catalog=[],references=[],epoch=0,detail=null,categoryControls=null,weatherControls=null,navigation=null,busy=false;
const cache=new Map();
const madrid=new Intl.DateTimeFormat('es-ES',{timeZone:'Europe/Madrid',dateStyle:'medium',timeStyle:'medium'});
function text(node,value){node.textContent=value;}
async function get(url){const response=await fetch(url,{cache:'no-store'});if(!response.ok)throw Error(`HTTP ${response.status}`);return response.json();}
function empty(){return {type:'FeatureCollection',features:[]};}
function setLayer(key,data){cache.set(key,data);categoryControls?.update(key,data);map.getSource(key).setData(data);}
function note(key,message,error=false){const node=$('status-'+key);text(node,message);node.classList.toggle('error',error);}
function reorder(){for(const row of [...$('layers').children].reverse())map.moveLayer('draw-'+row.dataset.id);}
function syncCredits(){const values=['Natural Earth'];if(['rail','roads'].includes(navigation.current().id))values.push('© IGN-CNIG');for(const id of navigation.current().sources){const data=cache.get(id);if(data?.features.length)values.push(data.attribution||catalog.find(l=>l.id===id).attribution);}if(navigation.current().id==='weather')values.push('© DWD · ICON');text($('map-attribution'),values.join(' · '));}
function fit(){
 const points=[];for(const [key,data] of cache){if(navigation?!navigation.isVisible(key):!$('toggle-'+key).checked)continue;for(const feature of categoryControls?.filter(key,data.features)||data.features){const g=feature.geometry;if(g.type==='Point')points.push(g.coordinates);else if(g.type==='LineString')points.push(...g.coordinates);else if(g.type==='MultiLineString')points.push(...g.coordinates.flat());}}
 if(points.length){const bounds=new maplibregl.LngLatBounds();points.forEach(p=>bounds.extend(p));map.fitBounds(bounds,{padding:innerWidth>850?{left:document.body.classList.contains('controls-closed')?45:350,right:45,top:45,bottom:45}:45,maxZoom:12,duration:0});}
}
async function render({automatic=false}={}){
 if(automatic&&busy)return;busy=true;
 if(!automatic)detail?.close();
 const sequence=++epoch;document.body.dataset.rendered='false';$('domain-panel').setAttribute('aria-busy','true');
 try{
  await Promise.allSettled([
   weatherControls?.update(navigation.weatherActive()),
   ...catalog.filter(layer=>navigation.sourceActive(layer.id)).map(async layer=>{
    try{
     const data=await get(`api/layers/${layer.id}?mode=archive`);if(sequence!==epoch)return;
     setLayer(layer.id,data);
     const received=data.received_at?madrid.format(new Date(data.received_at)):null;
     note(layer.id,`${data.status==='unavailable'?'Sin datos disponibles':data.features.length+' elementos'}${data.capture_status==='stale'?' · datos antiguos':''}${data.attempt?.status==='error'?' · última actualización fallida':''}${received?' · recibido '+received:''}`);
    }catch(error){if(sequence!==epoch)return;setLayer(layer.id,empty());note(layer.id,'Fuente temporalmente no disponible',true);}
   })
  ]);
  if(sequence!==epoch)return;
  navigation.sync();syncCredits();detail?.refresh(cache);
  text($('live-status'),'Actualización automática cada 30 s · '+madrid.format(new Date()));
 }finally{
  if(sequence===epoch){document.body.dataset.rendered='true';$('domain-panel').setAttribute('aria-busy','false');document.body.dataset.mode='live';busy=false;}
 }
}
map.on('load',async()=>{
 try{
  catalog=await get('api/layers');
  references=await get('api/reference-layers');
  for(const item of references){
   map.addSource('reference-'+item.id,{type:'raster',tiles:item.tiles.map(url=>decodeURIComponent(new URL(url,location.href).href)),tileSize:256,minzoom:0,maxzoom:15});
   map.addLayer({id:'reference-'+item.id,source:'reference-'+item.id,type:'raster',layout:{visibility:'none'},paint:{'raster-opacity':item.id==='railway'?1:0.7}});
   const row=document.createElement('div');row.className='layer';
   const label=document.createElement('label');label.className='layer-title';const check=document.createElement('input');check.type='checkbox';check.checked=true;check.id='reference-'+item.id;
   label.append(check,document.createTextNode(item.title));row.append(label);
   check.onchange=()=>navigation.sync();
   const opacity=document.createElement('input');opacity.type='range';opacity.min=0;opacity.max=100;opacity.value=item.id==='railway'?100:70;opacity.setAttribute('aria-label','Opacidad '+item.title);
   opacity.oninput=()=>map.setPaintProperty('reference-'+item.id,'raster-opacity',Number(opacity.value)/100);row.append(opacity);
   const status=document.createElement('p');status.id='reference-status-'+item.id;status.textContent='© IGN-CNIG · cartografía de referencia';row.append(status);$('references').append(row);
  }
  for(const layer of catalog){
   map.addSource(layer.id,{type:'geojson',data:empty()});const line=layer.id==='roads';
   map.addLayer({id:'draw-'+layer.id,source:layer.id,type:line?'line':'circle',paint:line?{'line-color':layer.color,'line-width':4}:{'circle-color':layer.color,'circle-radius':7,'circle-stroke-color':'#fff','circle-stroke-width':1}});
   const row=document.createElement('div');row.className='layer';row.dataset.id=layer.id;
   const label=document.createElement('label');label.className='layer-title';const check=document.createElement('input');check.type='checkbox';check.checked=layer.id!=='weather';check.id='toggle-'+layer.id;
   const swatch=document.createElement('span');swatch.className='swatch';swatch.style.background=layer.color;label.append(check,swatch,document.createTextNode(layer.id==='weather'?'Predicción puntual · MET Norway':layer.title));row.append(label);
   if(layer.id==='weather')map.setLayoutProperty('draw-weather','visibility','none');
   check.addEventListener('change',()=>navigation.sync());
   const status=document.createElement('p');status.id='status-'+layer.id;status.className='status';row.append(status);
   const tools=document.createElement('div');tools.className='layer-tools';const opacity=document.createElement('input');opacity.type='range';opacity.min=0;opacity.max=100;opacity.value=100;opacity.setAttribute('aria-label','Opacidad '+layer.title);
   opacity.addEventListener('input',()=>map.setPaintProperty('draw-'+layer.id,line?'line-opacity':'circle-opacity',Number(opacity.value)/100));tools.append(opacity);
   for(const [title,delta] of [['Subir',-1],['Bajar',1]]){const button=document.createElement('button');button.className='order';text(button,delta<0?'↑':'↓');button.setAttribute('aria-label',title+' '+layer.title);button.onclick=()=>{let sibling=delta<0?row.previousElementSibling:row.nextElementSibling;while(sibling?.hidden)sibling=delta<0?sibling.previousElementSibling:sibling.nextElementSibling;if(sibling){if(delta<0)sibling.before(row);else sibling.after(row);}reorder();};tools.append(button);}
   const settings=document.createElement('details');settings.className='layer-settings';const settingsTitle=document.createElement('summary');settingsTitle.textContent='Opciones de capa';settings.append(settingsTitle,tools);const attribution=document.createElement('p');text(attribution,layer.attribution);settings.append(attribution);row.append(settings);$('layers').append(row);
   map.on('mouseenter','draw-'+layer.id,()=>{map.getCanvas().style.cursor='pointer';});map.on('mouseleave','draw-'+layer.id,()=>{map.getCanvas().style.cursor='';});
  }
  reorder();detail=inspector(map,catalog);
  navigation=domains(map,catalog,{onChange:async(domain,{navigation:changed})=>{await render();if(changed&&navigation.current().id===domain.id)fit();}});navigation.sync();
  map.on('click',event=>{const clicked=map.queryRenderedFeatures(event.point,{layers:catalog.map(l=>'draw-'+l.id)})[0];if(!clicked)return;const source=clicked.source;const feature=cache.get(source)?.features.find(f=>clicked.properties.feature_key?f.properties.feature_key===clicked.properties.feature_key:(f.properties.id||f.properties.train_id)===(clicked.properties.id||clicked.properties.train_id));if(feature)detail.select(source,feature,{focus:false});});
  $('fit').onclick=fit;
  $('panel-toggle').onclick=()=>{if(innerWidth<=850&&!$('selection-panel').hidden){detail.close();document.body.classList.remove('controls-closed');$('panel-toggle').setAttribute('aria-expanded','true');return;}const closed=document.body.classList.toggle('controls-closed');$('panel-toggle').setAttribute('aria-expanded',String(!closed));};
  setInterval(()=>{if(!document.hidden)render({automatic:true});},30000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)render({automatic:true});});
  document.body.dataset.ready='true';await render();fit();
 }catch(error){$('map-error').hidden=false;text($('map-error'),'No se pudo iniciar el visor. Recarga la página para volver a intentarlo.');}
});
map.on('error',event=>{if(event.sourceId?.startsWith('reference-')){const id=event.sourceId.replace('reference-','');const node=$('reference-status-'+id);if(node)text(node,'Servicio IGN no disponible en esta zona; las demás capas siguen funcionando.');return;}if(event.sourceId?.startsWith('meteo-map-'))return;$('map-error').hidden=false;text($('map-error'),'No se pudo dibujar algún recurso del mapa.');});
