import { createMockBackend } from './engine';
import { deployment } from '../config/deployment';
// Umi never loads this module unless NODE_ENV=development AND ADMIN_MOCK=true.
const handle=createMockBackend();
type Request={method:string;path?:string;url:string;headers:Record<string,string|undefined>;query:Record<string,unknown>;body:unknown};
type Response={status:(code:number)=>Response;setHeader:(key:string,value:string)=>void;json:(value:unknown)=>void;end:()=>void};
function respond(req:Request,res:Response) {
 const fullPath=(req.path??req.url.split('?')[0]);
 const path=fullPath.startsWith(deployment.apiBase)?fullPath.slice(deployment.apiBase.length):fullPath;
 const response=handle({method:req.method,path,headers:req.headers,query:req.query,body:req.body});
 res.setHeader('Cache-Control','no-store');
 for(const [key,value]of Object.entries(response.headers??{}))res.setHeader(key,value);
 res.status(response.status);if(response.body===undefined)res.end();else res.json(response.body);
}
export default {
 [`GET ${deployment.apiBase}/*`]:respond,
 [`POST ${deployment.apiBase}/*`]:respond,
 [`PATCH ${deployment.apiBase}/*`]:respond,
 'GET /__admin_mock/help':respond,
 'POST /__admin_mock/scenario':respond,
};
