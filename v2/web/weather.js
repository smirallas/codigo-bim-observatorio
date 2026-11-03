const $=id=>document.getElementById(id);
const fmt=new Intl.DateTimeFormat('es-ES',{timeZone:'Europe/Madrid',dateStyle:'short',timeStyle:'short'});
export function weatherMaps(map){
 const root=$('weather-controls');root.className='weather-box';
 const heading=document.createElement('h3');heading.textContent='Mapas meteorológicos · predicción';root.append(heading);
 const status=document.createElement('p');status.textContent='Consultando los mapas disponibles…';root.append(status);
 const boxes=new Map();let capture=null,enabled=false;
 for(const [key,title] of [['temperature','Temperatura a 2 m'],['rain','Precipitación en la hora previa'],['wind','Velocidad del viento']]){
  const box=document.createElement('div');box.className='layer';
  const label=document.createElement('label');label.className='layer-title';const check=document.createElement('input');check.type='checkbox';check.id='meteo-'+key;label.append(check,document.createTextNode(title));box.append(label);
  const details=document.createElement('details');details.open=false;const summary=document.createElement('summary');summary.textContent='Validez, opacidad y escala';details.append(summary);
  const times=document.createElement('select');times.setAttribute('aria-label','Validez '+title);details.append(times);
  const opacity=document.createElement('input');opacity.type='range';opacity.min=0;opacity.max=100;opacity.value=key==='wind'?85:45;opacity.setAttribute('aria-label','Opacidad '+title);details.append(opacity);
  const info=document.createElement('p');details.append(info);
  const legend=document.createElement('img');legend.alt='Escala AEMET · '+title;legend.className='weather-legend';legend.hidden=true;legend.onerror=()=>{legend.hidden=true;};details.append(legend);box.append(details);root.append(box);
  const state={check,times,opacity,info,legend,item:null,manualTime:false};boxes.set(key,state);
  const redraw=()=>{
   if(!state.item||!capture)return;
   const visible=enabled&&check.checked;const id='meteo-map-'+key;
   const query=new URLSearchParams({valid:times.value});
   const tiles=[new URL(`api/weather/image/${capture}/${key}/{z}/{x}/{y}.png?${query}`,location.href).href.replaceAll('%7B','{').replaceAll('%7D','}')];
   if(!map.getSource(id)){map.addSource(id,{type:'raster',tiles,tileSize:256,maxzoom:10});map.addLayer({id,source:id,type:'raster',layout:{visibility:'none'},paint:{'raster-opacity':Number(opacity.value)/100}},'reference-railway');}
   else if(state.tileKey!==tiles[0])map.getSource(id).setTiles(tiles);
   state.tileKey=tiles[0];map.setLayoutProperty(id,'visibility',visible?'visible':'none');
   if(visible){legend.src=`api/weather/image/${capture}/${key}/legend.png?${query}`;legend.hidden=false;}else legend.hidden=true;
  };
  state.redraw=redraw;check.onchange=redraw;times.onchange=()=>{state.manualTime=true;redraw();};opacity.oninput=()=>{if(map.getLayer('meteo-map-'+key))map.setPaintProperty('meteo-map-'+key,'raster-opacity',Number(opacity.value)/100);};
 }
 const attribution=document.createElement('p');attribution.textContent='© AEMET · HARMONIE-AROME. Península, Baleares y Canarias. Lluvia acumulada en la hora previa; viento en km/h. Predicción, no observación ni radar.';root.append(attribution);
 map.on('error',event=>{if(event.sourceId?.startsWith('meteo-map-'))status.textContent='El servicio de mapas no ha podido dibujar alguna tesela. Las demás capas siguen disponibles.';});
 return {async update(active){
  enabled=active;
  for(const [key,s] of boxes){s.check.disabled=!active;if(map.getLayer('meteo-map-'+key))map.setLayoutProperty('meteo-map-'+key,'visibility',active&&s.check.checked?'visible':'none');}
  if(!active){status.textContent='Activa Meteorología para consultar los mapas.';return;}
  try{
   const response=await fetch('api/weather/maps',{cache:'no-store'});if(!response.ok)throw Error('sin metadatos');const data=await response.json();
   if(!enabled)return;
   if(data.status!=='available'){status.textContent=data.note;return;}
   const changed=capture!==data.capture_id;capture=data.capture_id;
   status.textContent=data.maps.some(m=>m.model_stale)?'Los archivos de AEMET tienen más de 18 horas. Comprueba su validez.':'Predicción AEMET disponible. Las capas se activan por separado.';
   for(const item of data.maps){const s=boxes.get(item.id);s.item=item;s.info.textContent='Archivos actualizados: '+fmt.format(new Date(item.generated_at))+' (Madrid). '+item.unit+'. Salida del modelo no identificada en la descarga.';
    if(changed||!s.times.options.length){const selected=s.times.value;s.times.replaceChildren();for(const valid of item.times){const option=document.createElement('option');option.value=valid;option.textContent=fmt.format(new Date(valid))+' · Madrid';s.times.append(option);}if(s.manualTime&&item.times.includes(selected))s.times.value=selected;else s.manualTime=false;}
    if(!s.manualTime)s.times.value=item.selected_time;
    s.redraw();
   }
  }catch(error){status.textContent='Mapas meteorológicos no disponibles. No se sustituye la malla por un punto coloreado.';}
 }};
}
