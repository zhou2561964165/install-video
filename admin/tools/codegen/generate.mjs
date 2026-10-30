import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import yaml from './node_modules/js-yaml/index.js';
import openapiTS, { astToString } from './node_modules/openapi-typescript/dist/index.mjs';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const source = path.resolve(root, '../docs/production/admin-api-v1.openapi.yaml');
const raw=fs.readFileSync(source,'utf8'),sha=createHash('sha256').update(raw).digest('hex');
if(sha!=='abb014bde928a0f68b78e83aa8db3067f4d392b03d99aa9024b705b63d9e8c4d')throw new Error('Frozen local contract hash changed; align the contract before codegen');
const document = yaml.load(raw);
const resolve = (value) => value?.$ref ? value.$ref.slice(2).split('/').reduce((o,k)=>o[k],document) : value;
fs.mkdirSync(path.join(root,'src/services/admin'),{recursive:true});
const typeSource=astToString(await openapiTS(new URL(`file:///${source.replaceAll('\\','/')}`))) + "\nexport type Schemas = components['schemas'];\n";
const operations = {};
for (const [url, methods] of Object.entries(document.paths)) {
  for (const [method, operation] of Object.entries(methods)) {
    const query = Object.fromEntries((operation.parameters ?? []).map(resolve).filter(p=>p.in==='query').map(p=>[p.name, resolve(p.schema)]));
    operations[operation.operationId] = {path:url,method:method.toUpperCase(),permission:operation['x-permission']??null,query};
  }
}
const operationSource='// Generated from the local OpenAPI candidate. Do not hand edit.\nexport const contractOperations = '+JSON.stringify(operations,null,2)+' as const;\n';
for(const [name,output]of Object.entries({'types.ts':typeSource,'contract.ts':operationSource})) {
 const destination=path.join(root,'src/services/admin',name);
 if(process.argv.includes('--check')) {if(fs.readFileSync(destination,'utf8')!==output)throw new Error(`${name} differs from the frozen contract`);}
 else fs.writeFileSync(destination,output);
}
console.log(`${process.argv.includes('--check')?'Checked':'Generated'} ${Object.keys(operations).length} operations; contract SHA256 ${sha}`);
