const {app,BrowserWindow,dialog}=require('electron');
const fs=require('fs');
const path=require('path');
const defaultTarget='http://127.0.0.1:4173/';
function readTarget(){
  const candidates=[];
  if(process.env.BSCH_SERVER_URL) candidates.push(process.env.BSCH_SERVER_URL);
  candidates.push(path.join(path.dirname(process.execPath),'server-url.txt'));
  candidates.push(path.join(__dirname,'server-url.txt'));
  for(const file of candidates){
    try{const value=process.env.BSCH_SERVER_URL||fs.readFileSync(file,'utf8').trim();if(value)return value.endsWith('/')?value:value+'/';}catch(_e){}
  }
  return defaultTarget;
}
const target=readTarget();
function create(){const win=new BrowserWindow({width:1100,height:760,show:false,backgroundColor:'#f5f8fb',webPreferences:{nodeIntegration:false,contextIsolation:true}});win.once('ready-to-show',()=>win.show());win.loadURL(target).catch(()=>dialog.showErrorBox('BSCH Clinics','تعذر الاتصال بالخادم: '+target+'\nأنشئ ملف server-url.txt بجوار البرنامج وضع فيه عنوان خادم المستشفى الداخلي.'));}
app.on('ready',create);app.on('window-all-closed',()=>{if(process.platform!=='darwin')app.quit()});
