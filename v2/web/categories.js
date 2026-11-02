const palette=['#126b60','#b26e16','#7059a2','#256da4','#b24454','#65812a','#896241','#178b98','#c0622a','#505f82'];
const missing='Sin dato';
const fixed={AVE:'#145e9c','AVE INT':'#5863a5',AVLO:'#81258f',ALVIA:'#1c7760',AVANT:'#df8e12',MD:'#8b5b2b',REGIONAL:'#829d37','REG.EXP.':'#b0434c',Intercity:'#206d75',EUROMED:'#b66124',PROXIMDAD:'#716b56',accident:'#b52e39',roadMaintenance:'#ba7414',poorEnvironment:'#277cac',obstruction:'#7957a4',environmentalObstruction:'#386c62',infrastructureDamageObstruction:'#914c3e',roadOrCarriagewayOrLaneManagement:'#9d704b',vehicleObstruction:'#935c9e',abnormalTraffic:'#b34a28'};
const titles={service_type:'Servicio',operator:'Operador',current_status:'Estado',aircraft_category:'Categoría ADS-B',aircraft_type:'Modelo publicado',altitude_band:'Banda de altitud',label:'Tipo',cause:'Causa',province:'Provincia'};
const fields={rail:['service_type','operator','current_status'],flights:['aircraft_category','aircraft_type','operator','altitude_band'],dgt:['cause','label','province']};
const labels={environmentalObstruction:'Obstáculo ambiental',infrastructureDamageObstruction:'Daños en la infraestructura',roadOrCarriagewayOrLaneManagement:'Gestión de carriles',vehicleObstruction:'Vehículo que obstruye',PROXIMDAD:'Proximidad',MD:'Media Distancia',STOPPED_AT:'En parada',IN_TRANSIT_TO:'En tránsito',INCOMING_AT:'Aproximándose',roadMaintenance:'Mantenimiento',accident:'Accidente',poorEnvironment:'Meteorología adversa',abnormalTraffic:'Tráfico anómalo',obstruction:'Obstáculo',RoadOrCarriagewayOrLaneManagement:'Gestión de carriles',MaintenanceWorks:'Obras',Accident:'Accidente',ConstructionWorks:'Construcción',GeneralObstruction:'Obstáculo',VehicleObstruction:'Vehículo en la vía',PoorEnvironmentConditions:'Condiciones ambientales',AbnormalTraffic:'Tráfico anómalo',A0:'Sin categoría detallada',A1:'Ligera',A2:'Pequeña',A3:'Grande',A4:'Alta estela',A5:'Pesada',A6:'Altas prestaciones',A7:'Helicóptero',B1:'Planeador',B2:'Más ligera que el aire',B3:'Paracaidista',B4:'Ultraligera',B6:'Aeronave no tripulada',C1:'Vehículo de emergencia en tierra',C2:'Vehículo de servicio en tierra'};
export function categoryLabel(value){return labels[value]||value;}
const value=(p,key)=>String(p[key]==null||p[key]===''?missing:p[key]);
function color(key){if(key===missing)return '#83908b';if(fixed[key])return fixed[key];let hash=0;for(const ch of key)hash=(hash*31+ch.charCodeAt(0))>>>0;return palette[hash%palette.length];}
const expression=field=>['case',['==',['get',field],''],missing,['to-string',['coalesce',['get',field],missing]]];
export function categories(map,catalog,{onChange}={}){
 const states=new Map();let interactive=true;
 for(const layer of catalog){
  if(!fields[layer.id])continue;
  const row=document.querySelector(`#layers [data-id="${layer.id}"]`);
  const state={field:fields[layer.id][0],filters:{},filterEnabled:{},categories:new Map(),data:null};states.set(layer.id,state);
  for(const field of fields[layer.id])state.categories.set(field,{enabled:true,selected:null});
  const coloring=document.createElement('select');coloring.setAttribute('aria-label','Colorear '+layer.title);
  for(const field of ['',...fields[layer.id]]){const option=document.createElement('option');option.value=field;option.textContent=field?'Color por '+titles[field].toLowerCase():'Un solo color';coloring.append(option);}coloring.value=state.field;row.append(coloring);
  const categoryBox=document.createElement('details');categoryBox.open=true;categoryBox.className='category-options';
  const categorySummary=document.createElement('summary');categoryBox.append(categorySummary);
  const categorySwitchLabel=document.createElement('label');categorySwitchLabel.className='filter-switch';const categorySwitch=document.createElement('input');categorySwitch.type='checkbox';categorySwitchLabel.append(categorySwitch,document.createTextNode('Aplicar esta selección'));categoryBox.append(categorySwitchLabel);
  const actions=document.createElement('div');actions.className='category-actions';
  for(const [label,all] of [['Todas',true],['Ninguna',false]]){const button=document.createElement('button');button.type='button';button.textContent=label;button.setAttribute('aria-label',(all?'Mostrar todas':'Ocultar todas')+' las categorías de '+layer.title);button.onclick=()=>{const c=state.categories.get(state.field);c.enabled=true;c.selected=all?null:new Set();paint(true);};actions.append(button);}categoryBox.append(actions);
  const legend=document.createElement('div');legend.className='legend category-checks';legend.setAttribute('aria-label','Leyenda '+layer.title);categoryBox.append(legend);row.append(categoryBox);
  const chips=document.createElement('div');chips.className='saved-filters';row.append(chips);
  const filters=document.createElement('details');filters.className='advanced-filters';const summary=document.createElement('summary');summary.textContent='Más filtros';filters.append(summary);row.append(filters);
  const controls=new Map();
  for(const field of fields[layer.id]){
   const block=document.createElement('div');block.className='individual-filter';
   const label=document.createElement('label');label.className='filter-switch';const check=document.createElement('input');check.type='checkbox';check.setAttribute('aria-label','Aplicar filtro de '+titles[field].toLowerCase()+' de '+layer.title);label.append(check,document.createTextNode(titles[field]));
   const select=document.createElement('select');select.setAttribute('aria-label','Filtrar '+layer.title+' por '+titles[field].toLowerCase());block.append(label,select);filters.append(block);controls.set(field,{select,check});
   select.onchange=()=>{state.filters[field]=select.value;state.filterEnabled[field]=select.value!=='';paint(true);};check.onchange=()=>{state.filterEnabled[field]=check.checked;paint(true);};
  }
  const reset=document.createElement('button');reset.type='button';reset.className='reset-filters';reset.textContent='Restablecer filtros';reset.setAttribute('aria-label','Restablecer filtros de '+layer.title);reset.onclick=()=>{state.filters={};state.filterEnabled={};for(const c of state.categories.values()){c.enabled=true;c.selected=null;}for(const c of controls.values())c.select.value='';paint(true);};filters.append(reset);
  const count=document.createElement('p');count.className='filter-count';count.setAttribute('role','status');row.append(count);
  const note=document.createElement('p');note.className='source-note';if(layer.id==='rail')note.textContent='Fuente: Renfe AV/LD/MD.';if(layer.id==='flights')note.textContent='Operador desconocido si la fuente no lo publica. Cobertura acotada al recurso consultado.';row.append(note);
  function matches(p){
   if(!interactive)return true;
   return fields[layer.id].every(field=>{const v=value(p,field),c=state.categories.get(field);return (!state.filterEnabled[field]||!state.filters[field]||v===state.filters[field])&&(!c.enabled||c.selected===null||c.selected.has(v));});
  }
  state.matches=matches;
  function paint(notify=false){
   if(!state.data)return;
   const focused=document.activeElement;const focusLabel=(legend.contains(focused)||chips.contains(focused))?focused.getAttribute('aria-label'):null;
   const clauses=[];
   for(const field of fields[layer.id]){if(state.filterEnabled[field]&&state.filters[field])clauses.push(['==',expression(field),state.filters[field]]);const c=state.categories.get(field);if(c.enabled&&c.selected!==null)clauses.push(['in',expression(field),['literal',[...c.selected]]]);controls.get(field).check.checked=!!state.filterEnabled[field];}
   map.setFilter('draw-'+layer.id,interactive&&clauses.length?['all',...clauses]:null);
   const counts=new Map();for(const f of state.data.features){const key=state.field?value(f.properties,state.field):missing;counts.set(key,(counts.get(key)||0)+1);}
   const keys=[...counts.keys()].sort((a,b)=>categoryLabel(a).localeCompare(categoryLabel(b),'es'));
   map.setPaintProperty('draw-'+layer.id,'circle-color',!interactive||!state.field?layer.color:keys.length?['match',expression(state.field),...keys.flatMap(key=>[key,color(key)]),'#83908b']:'#83908b');
   categoryBox.hidden=!interactive||!state.field;filters.hidden=!interactive;chips.hidden=!interactive;coloring.disabled=!interactive;
   if(state.field){
    const c=state.categories.get(state.field);categorySummary.textContent='Categorías de '+titles[state.field].toLowerCase();categorySwitch.checked=c.enabled;categorySwitch.setAttribute('aria-label','Aplicar categorías de '+titles[state.field].toLowerCase()+' de '+layer.title);
    legend.replaceChildren();for(const key of keys){const label=document.createElement('label');label.className='category-item';const check=document.createElement('input');check.type='checkbox';check.checked=c.selected===null||c.selected.has(key);check.setAttribute('aria-label','Mostrar '+categoryLabel(key)+' en '+layer.title);const swatch=document.createElement('i');swatch.style.background=color(key);const title=document.createElement('span');title.textContent=categoryLabel(key);const n=document.createElement('small');n.textContent=counts.get(key);label.append(check,swatch,title,n);check.onchange=()=>{if(c.selected===null)c.selected=new Set(keys);if(check.checked)c.selected.add(key);else c.selected.delete(key);c.enabled=true;paint(true);};legend.append(label);}
   }
   chips.replaceChildren();for(const [field,c] of state.categories){if(c.selected===null)continue;const label=document.createElement('label');label.className='filter-chip';const check=document.createElement('input');check.type='checkbox';check.checked=c.enabled;check.setAttribute('aria-label','Activar selección guardada de '+titles[field].toLowerCase()+' de '+layer.title);check.onchange=()=>{c.enabled=check.checked;paint(true);};label.append(check,document.createTextNode(titles[field]+': selección guardada'));chips.append(label);}
   const shown=state.data.features.filter(f=>matches(f.properties)).length;count.textContent=`${shown} de ${state.data.features.length} coinciden con los filtros`;
   if(!interactive)count.textContent='Ejemplo sintético · selección de categorías desactivada';
   if(focusLabel)[...row.querySelectorAll('input[aria-label]')].find(n=>n.getAttribute('aria-label')===focusLabel)?.focus({preventScroll:true});
   if(notify)onChange?.(layer.id);
  }
  coloring.onchange=()=>{state.field=coloring.value;paint(true);};categorySwitch.onchange=()=>{state.categories.get(state.field).enabled=categorySwitch.checked;paint(true);};
  state.update=data=>{
   state.data=data;
   for(const feature of data.features){const p=feature.properties;if(layer.id==='flights')p.altitude_band=p.altitude_m==null?null:p.altitude_m<1000?'Menos de 1.000 m':p.altitude_m<5000?'1.000–5.000 m':p.altitude_m<10000?'5.000–10.000 m':'Más de 10.000 m';}
   for(const [field,{select}] of controls){const selected=state.filters[field]||'';select.replaceChildren();const all=document.createElement('option');all.value='';all.textContent='Todos';select.append(all);const keys=[...new Set(data.features.map(f=>value(f.properties,field)))].sort();if(selected&&!keys.includes(selected))keys.push(selected);for(const key of keys){const option=document.createElement('option');option.value=key;option.textContent=categoryLabel(key);select.append(option);}select.value=selected;}
   paint();
  };
  state.paint=paint;
 }
 return {setInteractive(value){interactive=value;for(const state of states.values())state.paint();},update(key,data){states.get(key)?.update(data);},filter(key,features){const state=states.get(key);return state?features.filter(f=>state.matches(f.properties)):features;}};
}
