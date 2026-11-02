// Test-only injection. Not copied into runtime image.
const Module=require('module'),original=Module._load,fs=require('fs');
global.fetch=async()=>({ok:true,json:async()=>({id:'fixture-account'})});
Module._load=function(name,parent,...rest){
 const real=original.call(this,name,parent,...rest);
 if(name==='./runner.cjs'&&parent.filename.endsWith('/runtime/cloud.cjs')){
  return {...real,loadRuntime(store){const e={cfg:{mode:'paper'},positions:[],orders:[],connected:false,armed:false,locked:true,reconciled:true,leaseName:'fixture',async connect(keys,options){this.connected=true;this.armed=options.startPaper},async save(){},async pause(){this.armed=false},async startPaper(){this.armed=true},stop(s){this.armed=false;this.halt=s}};return {engine:e,supervisor:{state:{status:'OFF'},async request(){throw Error('No gateway configured')},async load(){},async pulse(){}}};}};
 }
 return real;
};
