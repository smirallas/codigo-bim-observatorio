// La navegación se deriva de las fuentes que incluye cada entrega, no de un calendario.
export const DOMAINS=[
 {id:'rail',title:'Trenes',description:'Posiciones publicadas por Renfe y trazado ferroviario.',sources:['rail'],references:['railway']},
 {id:'roads',title:'Carreteras / DGT',description:'Red viaria e incidencias publicadas por la DGT.',sources:['roads','dgt'],references:['highways']},
 {id:'flights',title:'Aviones',description:'Aeronaves y categorías disponibles en el recurso consultado.',sources:['flights'],references:[]},
 {id:'weather',title:'Meteorología',description:'Temperatura, precipitación y viento, con su validez.',sources:['weather'],references:[]},
];

export function domains(map,catalog,{onChange}={}){
 const $=id=>document.getElementById(id);
 const available=DOMAINS.filter(d=>d.sources.some(s=>catalog.some(l=>l.id===s)));
 const viewKeys={trenes:'rail',carreteras:'roads',aviones:'flights',meteorologia:'weather'};
 const requested=viewKeys[new URLSearchParams(location.search).get('vista')];
 let active=available.find(d=>d.id===requested)?.id||available[0]?.id;const enabled=new Map(available.map(d=>[d.id,true]));
 const buttons=new Map();
 function current(){return available.find(d=>d.id===active);}
 function sync(){
  const domain=current();if(!domain)return;
  const visible=enabled.get(active);
  document.body.dataset.domain=active;
  $('domain-panel').setAttribute('aria-labelledby','tab-'+active);
  $('domain-title').textContent=domain.title;$('domain-description').textContent=domain.description;
  $('domain-enabled').checked=visible;$('domain-enabled-label').textContent='Mostrar '+domain.title.toLowerCase();
  for(const [id,button] of buttons){const selected=id===active;button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;}
  for(const layer of catalog){
   const inDomain=domain.sources.includes(layer.id);const row=$('layers').querySelector(`[data-id="${layer.id}"]`);row.hidden=!inDomain||layer.id==='weather';
   for(const button of row.querySelectorAll('button.order'))button.hidden=domain.sources.filter(s=>catalog.some(l=>l.id===s)).length<2;
   const data=$('data-'+layer.id);if(data)data.hidden=!inDomain;
   map.setLayoutProperty('draw-'+layer.id,'visibility',inDomain&&visible&&$('toggle-'+layer.id).checked?'visible':'none');
  }
  for(const item of ['railway','highways']){
   const check=$('reference-'+item);if(!check)continue;
   const inDomain=domain.references.includes(item);check.closest('.layer').hidden=!inDomain;
   map.setLayoutProperty('reference-'+item,'visibility',inDomain&&visible&&check.checked?'visible':'none');
  }
  if(map.getLayer('trajectory'))map.setLayoutProperty('trajectory','visibility',active==='rail'&&visible?'visible':'none');
  $('weather-controls').hidden=active!=='weather';
 }
 function select(id){if(!available.some(d=>d.id===id)||id===active)return;active=id;const url=new URL(location.href);url.searchParams.set('vista',Object.keys(viewKeys).find(k=>viewKeys[k]===id));history.replaceState(null,'',url);sync();onChange?.(current(),{navigation:true});}
 for(const [index,domain] of available.entries()){
  const button=document.createElement('button');button.type='button';button.id='tab-'+domain.id;button.setAttribute('role','tab');button.setAttribute('aria-controls','domain-panel');button.textContent=domain.title;
  button.onclick=()=>select(domain.id);
  button.onkeydown=event=>{let next;if(event.key==='ArrowRight'||event.key==='ArrowDown')next=(index+1)%available.length;else if(event.key==='ArrowLeft'||event.key==='ArrowUp')next=(index+available.length-1)%available.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=available.length-1;else return;event.preventDefault();select(available[next].id);buttons.get(available[next].id).focus();};
  buttons.set(domain.id,button);$('domain-tabs').append(button);
 }
 $('domain-enabled').onchange=()=>{enabled.set(active,$('domain-enabled').checked);sync();onChange?.(current(),{navigation:false});};
 return {sync,select,current,isVisible(source){return !!current()?.sources.includes(source)&&enabled.get(active)&&$('toggle-'+source).checked;},weatherActive(){return active==='weather'&&enabled.get(active);},sourceActive(source){return !!current()?.sources.includes(source);},referenceActive(id){return !!current()?.references.includes(id)&&enabled.get(active);}};
}
