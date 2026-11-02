namespace HGateway24 {
  export type Session = {authenticated:boolean; csrf?:string; expires?:number};
  export type Credentials = {url:string; token:string; mode?:'integrated'};
  export function localOrigin(origin:string):boolean {
    try {const u=new URL(origin); return u.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(u.hostname)&&u.origin===origin;}catch{return false;}
  }
  export function eligible(origin:string):boolean {
    try{const u=new URL(origin);return u.origin===origin&&(u.protocol==='https:'||localOrigin(origin));}catch{return false;}
  }
  export function route(path:string):string {
    if(!/^\/v1\/(?:bootstrap|session|logout|config|provider-check|health|review-policy|jobs(?:\/[A-Za-z0-9-]{1,80})?|reviews(?:\/[A-Za-z0-9-]{1,80})?)$/.test(path))throw Error('Ruta fuera del gateway HARPOON');
    return path;
  }
  export function connected(s:Session|null):boolean{return Boolean(s?.authenticated&&s.csrf&&s.expires&&s.expires*1000>Date.now());}
}
