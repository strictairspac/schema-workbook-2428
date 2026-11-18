import {api} from './client.js';
export const renamesApi={list:()=>api('/renames'),apply:(id,data)=>api('/relations/'+id+'/renames','POST',data)};
