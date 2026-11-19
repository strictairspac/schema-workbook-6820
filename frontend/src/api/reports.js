import {api} from './client.js';
export const reportsApi={
  list:()=>api('/reports'),
  detail:id=>api('/reports/'+id),
  create:data=>api('/reports','POST',data),
};
