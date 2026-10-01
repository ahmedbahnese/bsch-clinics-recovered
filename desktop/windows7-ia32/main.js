const {app,BrowserWindow,dialog}=require('electron');
const path=require('path');
const target=process.env.BSCH_SERVER_URL||'https://bsch-clinics-6io8.whacka.app/';
function create(){const win=new BrowserWindow({width:1100,height:760,show:false,backgroundColor:'#f5f8fb',webPreferences:{nodeIntegration:false,contextIsolation:true}});win.once('ready-to-show',()=>win.show());win.loadURL(target).catch(()=>dialog.showErrorBox('BSCH Clinics','تعذر الاتصال بالخادم: '+target));}
app.on('ready',create);app.on('window-all-closed',()=>{if(process.platform!=='darwin')app.quit()});
