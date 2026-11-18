import {renamesApi} from '../api/renames.js';
export const renamesStore={items:[],async refresh(){this.items=await renamesApi.list();return this.items;}};
