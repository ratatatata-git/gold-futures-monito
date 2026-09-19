const state = { data: [], period: "1M", selected: null };

const $ = id => document.getElementById(id);
const fmtInt = n => Number(n).toLocaleString("en-US");
const fmtPrice = n => Number(n).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});
const fmtDate = s => new Date(s+"T00:00:00").toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"});

async function init(){
  state.data = await fetch("data/demo-data.json").then(r=>r.json());
  bind();
  render();
  if("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(()=>{});
}

function bind(){
  document.querySelectorAll(".periods button").forEach(btn=>{
    btn.addEventListener("click",()=>{
      document.querySelectorAll(".periods button").forEach(b=>b.classList.remove("active"));
      btn.classList.add("active");
      state.period=btn.dataset.period;
      render();
    });
  });
  ["priceChart","volumeChart","oiChart"].forEach(id=>{
    $(id).addEventListener("click", e=>selectFromChart(id,e));
  });
}

function sliceData(){
  const counts={ "1M":22, "3M":66, "6M":132, "1Y":252 };
  return state.data.slice(-counts[state.period]);
}

function render(){
  const d = state.data[state.data.length-1];
  $("contract").textContent=d.contract;
  $("settlement").textContent="$"+fmtPrice(d.settlement);
  $("settlementDate").textContent=fmtDate(d.date);
  $("volume").textContent=fmtInt(d.volume);
  $("oi").textContent=fmtInt(d.open_interest);
  $("oiChange").textContent=(d.oi_change>=0?"+":"")+fmtInt(d.oi_change);
  const rows=sliceData();
  drawLine($("priceChart"),rows,"settlement",true);
  drawBars($("volumeChart"),rows,"volume");
  drawLine($("oiChart"),rows,"open_interest",false);
  if(state.selected) showDetail(state.selected);
}

function chartGeometry(canvas){
  const dpr=Math.max(1,devicePixelRatio||1), rect=canvas.getBoundingClientRect();
  canvas.width=Math.round(rect.width*dpr);canvas.height=Math.round(rect.height*dpr);
  const ctx=canvas.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0);
  return {ctx,w:rect.width,h:rect.height,pad:{l:45,r:8,t:8,b:25}};
}
function scale(values, min, max, y0, y1){
  return v=>y1-(v-min)/(max-min||1)*(y1-y0);
}
function baseChart(canvas, rows, key){
  const g=chartGeometry(canvas), {ctx,w,h,pad}=g;
  const vals=rows.map(r=>r[key]), min=Math.min(...vals), max=Math.max(...vals);
  const y=scale(vals,min,max,pad.t,pad.b?h-pad.b:h);
  const x=i=>pad.l+i*(w-pad.l-pad.r)/Math.max(1,rows.length-1);
  ctx.clearRect(0,0,w,h);ctx.font="10px -apple-system,BlinkMacSystemFont,sans-serif";
  ctx.strokeStyle="#252b33";ctx.fillStyle="#737e8c";ctx.lineWidth=1;
  for(let j=0;j<4;j++){const yy=pad.t+j*(h-pad.t-pad.b)/3;ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(w-pad.r,yy);ctx.stroke();
    const val=max-(max-min)*j/3;ctx.fillText(key==="settlement"?fmtPrice(val):fmtInt(Math.round(val)),3,yy+3);
  }
  const step=Math.max(1,Math.floor(rows.length/5));
  rows.forEach((r,i)=>{if(i%step===0||i===rows.length-1){ctx.fillText(r.date.slice(5),Math.max(pad.l-5,x(i)-12),h-6)}});
  return {g,x,y,min,max};
}
function drawLine(canvas,rows,key,price){
  const {g,x,y}=baseChart(canvas,rows,key),ctx=g.ctx;
  ctx.strokeStyle="#d8b46a";ctx.lineWidth=2;ctx.beginPath();
  rows.forEach((r,i)=>{const xx=x(i),yy=y(r[key]);i?ctx.lineTo(xx,yy):ctx.moveTo(xx,yy)});ctx.stroke();
  const last=rows.length-1;ctx.fillStyle="#f4f6f8";ctx.beginPath();ctx.arc(x(last),y(rows[last][key]),3.5,0,Math.PI*2);ctx.fill();
}
function drawBars(canvas,rows,key){
  const {g,x,y,min,max}=baseChart(canvas,rows,key),ctx=g.ctx;
  const bottom=g.h-g.pad.b, barW=Math.max(1,(g.w-g.pad.l-g.pad.r)/rows.length*.72);
  rows.forEach((r,i)=>{const yy=y(r[key]);ctx.fillStyle="#7f8b99";ctx.fillRect(x(i)-barW/2,yy,barW,bottom-yy)});
}
function selectFromChart(id,e){
  const rows=sliceData(), canvas=$(id), rect=canvas.getBoundingClientRect(), px=e.clientX-rect.left;
  const idx=Math.round((px-45)/(rect.width-45-8)*Math.max(0,rows.length-1));
  if(idx>=0&&idx<rows.length){state.selected=rows[idx];showDetail(rows[idx])}
}
function showDetail(d){
  const vals=[fmtDate(d.date),d.contract,"$"+fmtPrice(d.settlement),fmtInt(d.volume),fmtInt(d.open_interest),(d.oi_change>=0?"+":"")+fmtInt(d.oi_change)];
  document.querySelector("#detail .detail-grid").innerHTML=`
    <span>Date</span><b>${vals[0]}</b>
    <span>Contract</span><b>${vals[1]}</b>
    <span>Settlement</span><b>${vals[2]}</b>
    <span>Volume</span><b>${vals[3]}</b>
    <span>Open Interest</span><b>${vals[4]}</b>
    <span>OI Change</span><b>${vals[5]}</b>`;
}
window.addEventListener("resize",()=>render());
init();
