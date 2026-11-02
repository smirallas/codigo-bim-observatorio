// Ficha integrada. Los textos de las fuentes siempre se insertan como texto, nunca HTML.
import {categoryLabel} from './categories.js';
const $=id=>document.getElementById(id);
const date=new Intl.DateTimeFormat('es-ES',{timeZone:'Europe/Madrid',dateStyle:'medium',timeStyle:'medium'});
const number=new Intl.NumberFormat('es-ES',{maximumFractionDigits:1});
const unknown='No publicado';
function el(tag,value,className){const node=document.createElement(tag);if(value!=null)node.textContent=value;if(className)node.className=className;return node;}
function time(value){if(!value)return unknown;const parsed=new Date(value);return Number.isNaN(parsed.getTime())?String(value):date.format(parsed);}
function unit(value,suffix){return value==null||!Number.isFinite(Number(value))?unknown:number.format(Number(value))+' '+suffix;}
function group(parent,title,rows){const section=el('section');section.append(el('h3',title));const dl=el('dl');for(const [label,value] of rows){dl.append(el('dt',label),el('dd',value==null||value===''?unknown:String(value)));}section.append(dl);parent.append(section);}
const status={STOPPED_AT:'Detenido en la parada indicada',IN_TRANSIT_TO:'En tránsito hacia la parada indicada',INCOMING_AT:'Aproximándose a la parada indicada',0:'Aproximándose a la parada indicada',1:'Detenido en la parada indicada',2:'En tránsito hacia la parada indicada'};
const incidents={Accident:'Accidente',RoadOrCarriagewayOrLaneManagement:'Gestión de carretera o carril',MaintenanceWorks:'Obras de mantenimiento',ConstructionWorks:'Obras',AbnormalTraffic:'Tráfico anómalo',PoorEnvironmentConditions:'Condiciones ambientales adversas',GeneralObstruction:'Obstáculo',VehicleObstruction:'Vehículo que obstruye la vía'};
export function featureLabel(source,p){if(p.kind==='synthetic')return p.label||p.id;return source==='rail'?'Tren '+(p.label||p.train_id||p.id):source==='dgt'?(p.road_name?p.road_name+' · ':'')+(incidents[p.label]||'Incidencia de tráfico'):p.label||p.id||'Tramo';}
export function inspector(map,catalog){
 let serial=0,selected=null;
 map.addSource('selected-item',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
 map.addSource('candidate-segments',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
 map.addLayer({id:'candidate-segments',source:'candidate-segments',type:'line',paint:{'line-color':'#b17405','line-width':6,'line-opacity':0.85}});
 map.addLayer({id:'selected-line',source:'selected-item',type:'line',filter:['==',['geometry-type'],'LineString'],paint:{'line-color':'#efb93e','line-width':8}});
 map.addLayer({id:'selected-point',source:'selected-item',type:'circle',filter:['==',['geometry-type'],'Point'],paint:{'circle-color':'#fff','circle-opacity':0.1,'circle-radius':13,'circle-stroke-color':'#b17405','circle-stroke-width':4}});
 const empty=()=>({type:'FeatureCollection',features:[]});
 function close(){serial++;selected=null;$('selection-panel').hidden=true;delete document.body.dataset.selected;delete document.body.dataset.detailLoaded;map.getSource('selected-item').setData(empty());map.getSource('candidate-segments').setData(empty());}
 $('selection-close').onclick=close;
 document.addEventListener('keydown',event=>{if(event.key==='Escape')close();});
 new ResizeObserver(()=>map.resize()).observe($('map'));
 function association(data){
  const target=$('selection-network');target.replaceChildren();
  if(!data||data.status==='not_applicable')return;
  target.append(el('h3','Relación con la infraestructura'));
  const labels={candidate:'Tramo próximo · sin confirmar',ambiguous:'Varios tramos compatibles',reference_only:'Enlace cartográfico ficticio',not_found:'Sin candidato cercano',outside_coverage:'Cobertura no disponible'};
  const banner=el('p',labels[data.status]||'Sin asociación','quality');target.append(banner,el('p',data.message));
  if(data.method)target.append(el('p',data.method,'small'));
  const candidates=data.candidates||[];
  map.getSource('candidate-segments').setData({type:'FeatureCollection',features:candidates.map(c=>({type:'Feature',geometry:c.geometry,properties:{id:c.segment_id}}))});
  for(const [index,c] of candidates.entries()){
   const names=[...new Set((c.references||[]).map(r=>r.code||r.name).filter(Boolean))];
   const button=el('button',`${names.join(' / ')||'Tramo '+(index+1)} · ${unit(c.distance_m,'m')}${c.fictitious?' · ficticio':''}`,'segment-button');
   button.onclick=()=>{const coordinates=c.geometry.coordinates;const xs=coordinates.map(p=>p[0]),ys=coordinates.map(p=>p[1]);map.fitBounds([[Math.min(...xs),Math.min(...ys)],[Math.max(...xs),Math.max(...ys)]],{padding:55,maxZoom:16,duration:350});};
   target.append(button,el('p',c.segment_id,'identifier'));
   const ref=c.references?.[0];
   if(ref)target.append(el('p',[ref.name,ref.type,ref.gauge,ref.tracks?'N.º de vías en cartografía: '+ref.tracks:null].filter(Boolean).join(' · '),'small'));
  }
  if(data.network_imported_at)target.append(el('p','Red IGN-CNIG importada: '+time(data.network_imported_at)+' · Madrid','small'));
  if(data.attribution)target.append(el('p',data.attribution,'small'));
 }
 function draw(source,feature,capture,schedule,synthetic){
  const p=feature.properties;const body=$('selection-body');body.replaceChildren();
  const title=source==='rail'?'Tren '+(p.label||p.train_id||p.id):source==='flights'?'Vuelo '+(p.label||p.id):source==='weather'?'Predicción meteorológica':source==='dgt'?(incidents[p.label]||'Incidencia de tráfico'):(p.label||p.id||'Tramo viario');
  $('selection-title').textContent=title;
  $('selection-source').textContent=(synthetic?'EJEMPLO · ':'')+catalog.find(l=>l.id===source).title;
  if(synthetic)body.append(el('p','Datos inventados para probar el visor. No describen un tren ni una incidencia real.','quality'));
  else if(source==='rail'&&!p.observed_at)body.append(el('p','Renfe no publica la hora individual de esta posición. La hora del feed y la recepción no acreditan que el tren siga aquí.','quality'));
  if(source==='rail'){
   const trip=schedule?.trip;
   group(body,'El servicio',[
    ['Servicio',trip?.service_name],['Operador publicado',p.operator],['Origen planificado',trip?.origin],['Destino planificado',trip?.destination],
    ['Parada de referencia',schedule?.stop_name||p.stop_id],['Estado publicado',status[p.current_status]||p.current_status],
    ['Velocidad',unit(p.speed_m_s==null?null:p.speed_m_s*3.6,'km/h')],['Rumbo',unit(p.bearing_deg,'°')],['Vía física',p.track_id||'Sin identificar']]);
   if(!trip&&!synthetic)body.append(el('p','No hay un viaje coincidente en el horario importado. No se deducen el servicio, el origen ni el destino del número del tren.','small'));
   if(trip)group(body,'Horario planificado · no es puntualidad',[
    ['Salida',trip.scheduled_departure],['Llegada',trip.scheduled_arrival]]);
   const details=el('details');details.append(el('summary','Identificadores de la fuente'));
   group(details,'Referencia GTFS',[['Vehículo',p.id||p.train_id],['Viaje exacto',p.trip_id],['Ruta',p.route_id||trip?.route_id],['Parada',p.stop_id],['Secuencia de parada',p.stop_sequence]]);body.append(details);
  }else if(source==='flights'){
   group(body,'La aeronave',[['Indicativo',p.label],['Modelo publicado',p.aircraft_type],['Categoría ADS-B',p.aircraft_category?categoryLabel(p.aircraft_category):null],['Matrícula',p.registration],['Operador publicado',p.operator],['Identificador ICAO',p.id],['Velocidad sobre el suelo',unit(p.speed_m_s==null?null:p.speed_m_s*3.6,'km/h')],['Altitud',unit(p.altitude_m,'m')],['Referencia de altitud',p.altitude_basis==='barometric'?'Barométrica':p.altitude_basis],['Rumbo',unit(p.heading_deg,'°')],['En tierra',p.on_ground==null?unknown:p.on_ground?'Sí':'No']]);
  }else if(source==='weather'){
   group(body,'Predicción · no es una observación',[['Válida desde',time(p.valid_at)],['Temperatura',unit(p.temperature_c,'°C')],['Precipitación en 1 h',unit(p.precipitation_mm,'mm')],['Viento',unit(p.wind_km_h,'km/h')]]);
  }else if(source==='dgt'){
   if(p.description)body.append(el('p',p.description));
   group(body,'La incidencia',[['Tipo',incidents[p.label]||p.label],['Causa publicada',p.cause?categoryLabel(p.cause):null],['Carretera declarada',p.road_name],['Municipio',p.municipality],['Provincia',p.province],['PK inicial',p.start_pk],['PK final',p.end_pk],['Inicio de validez',time(p.valid_from)],['Fin de validez',time(p.valid_to)],['Actualización del registro',time(p.updated_at)]]);
   if(p.location_basis)body.append(el('p',p.location_basis,'small'));
  }else group(body,'El tramo',[['Nombre',p.label],['Referencia',p.ref||p.road_name],['Clasificación',p.highway||p.road_type],['Fuente',p.source]]);
  group(body,'Cuándo se conoce el dato · hora de Madrid',[
   ['Observación individual',time(p.observed_at)],['Publicación del conjunto',time(capture?.published_at||p.published_at)],['Recepción en la aplicación',time(capture?.received_at||p.received_at)]]);
  if(feature.geometry.type==='Point')group(body,'Posición publicada',[['Latitud',feature.geometry.coordinates[1].toFixed(6)],['Longitud',feature.geometry.coordinates[0].toFixed(6)]]);
  body.append(el('p',synthetic?'Código BIM · ejemplo sintético · MIT':(capture?.metadata?.attribution||catalog.find(l=>l.id===source).attribution),'small'));
 }
 async function select(source,feature,{focus=true}={}){
  const seq=++serial;const synthetic=false;
  selected={source,feature};
  delete document.body.dataset.detailLoaded;
  $('selection-panel').hidden=false;document.body.dataset.selected=source;
  map.getSource('selected-item').setData({type:'FeatureCollection',features:[feature]});
  map.getSource('candidate-segments').setData(empty());$('selection-network').replaceChildren();
  draw(source,feature,null,null,synthetic);
  if(focus&&feature.geometry.type==='Point')map.easeTo({center:feature.geometry.coordinates,zoom:Math.max(map.getZoom(),12),duration:350});
  if(matchMedia('(max-width: 850px)').matches)$('selection-panel').scrollIntoView({block:'nearest',behavior:'smooth'});
  if(synthetic)return;
  const p=feature.properties;if(!p.capture_id||p.ordinal==null)return;
  const query=new URLSearchParams();
  const loading=el('p','Buscando información del viaje y tramos candidatos…','small');$('selection-network').append(loading);
  try{
   const response=await fetch(`api/features/${source}/${p.capture_id}/${p.ordinal}?${query}`,{cache:'no-store'});
   if(!response.ok)throw Error('HTTP '+response.status);const result=await response.json();if(seq!==serial)return;
   draw(source,result.feature,result.capture,result.schedule,false);association(result.association);
   document.body.dataset.detailLoaded=source;
  }catch(error){if(seq===serial)$('selection-network').replaceChildren(el('p','No se pudo cargar la información adicional del elemento.','quality'));}
 }
 return {select,close,refresh(cache){if(!selected)return;const {source,feature}=selected,p=feature.properties;const matches=(cache.get(source)?.features||[]).filter(f=>{const q=f.properties;return source==='rail'?(p.entity_id?q.entity_id===p.entity_id:q.id===p.id)&&q.trip_id===p.trip_id:q.id===p.id;});if(matches.length===1&&matches[0].properties.capture_id!==p.capture_id)select(source,matches[0],{focus:false});else if(matches.length!==1){map.getSource('selected-item').setData(empty());$('selection-network').replaceChildren(el('p','Este elemento no aparece de forma unívoca en la última captura. Esta ficha conserva los tiempos de la captura anterior.','quality'));}}};
}
