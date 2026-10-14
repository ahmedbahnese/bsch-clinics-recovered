const {app,BrowserWindow}=require('electron');
const fs=require('fs');
const path=require('path');
const http=require('http');
const defaultTarget='http://127.0.0.1:4173/';
function normalize(value){return value.endsWith('/')?value:`${value}/`}
function readTargets(){
  const candidates=[];
  if(process.env.BSCH_SERVER_URL) candidates.push(process.env.BSCH_SERVER_URL);
  candidates.push(path.join(path.dirname(process.execPath),'server-url.txt'));
  candidates.push(path.join(__dirname,'server-url.txt'));
  for(const file of candidates){
    try{const value=process.env.BSCH_SERVER_URL||fs.readFileSync(file,'utf8').trim();if(value){const configured=normalize(value);return configured===defaultTarget?[defaultTarget]:[configured,defaultTarget]}}catch(_e){}
  }
  return [defaultTarget];
}
const targets=readTargets();
let target=targets[0];
function waitForServer(url, attempts=20, delay=500){return new Promise((resolve,reject)=>{const check=(left)=>{const request=http.get(url,{timeout:1200},response=>{response.resume();if(response.statusCode>=200&&response.statusCode<500)return resolve();retry(left)});request.on('error',()=>retry(left));request.on('timeout',()=>{request.destroy();retry(left)});function retry(remaining){if(remaining<=0)return reject(new Error('server_unavailable'));setTimeout(()=>check(remaining-1),delay)}};check(attempts)})}
function errorPage(){return `<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><title>BSCH Clinics</title><style>body{font-family:Tahoma,Arial;background:#f4f8f8;color:#17324d;padding:40px;line-height:1.9}.box{max-width:720px;margin:30px auto;background:white;border-radius:18px;padding:30px;box-shadow:0 8px 30px #17324d22}h1{color:#0f948b}code{direction:ltr;display:inline-block;background:#eef4f4;padding:4px 8px;border-radius:5px}</style><div class="box"><h1>BSCH Clinics</h1><h2>الخادم المحلي غير قيد التشغيل</h2><p>لم يتم العثور على خدمة تعمل على المنفذ 4173.</p><p>شغّل أولًا الملف <code>START-OFFLINE.bat</code>، ثم افتح البرنامج مرة أخرى.</p><p>تمت تجربة العناوين: <code>${targets.join('</code> و <code>')}</code></p></div></html>`}
async function create(){const win=new BrowserWindow({width:1100,height:760,show:false,backgroundColor:'#f5f8fb',webPreferences:{nodeIntegration:false,contextIsolation:true}});try{let connected=false;for(const candidate of targets){try{await waitForServer(candidate);target=candidate;connected=true;break}catch(_e){}}if(!connected)throw new Error('server_unavailable');await win.loadURL(target);win.show()}catch(_e){await win.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(errorPage())}`);win.show()}}
app.whenReady().then(create);app.on('window-all-closed',()=>{if(process.platform!=='darwin')app.quit()});
