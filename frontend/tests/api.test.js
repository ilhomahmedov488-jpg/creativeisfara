import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {ApiClient, ApiError} from '../static/studio/api.js';
import {estimate, countdown, localInput, apiDateTime, changeAllowed, safeMedia} from '../static/studio/domain.js';

const response = (body, status=200) => new Response(status===204?null:JSON.stringify(body), {status});

test('session requests use cookies, CSRF rotates after login, and logout accepts 204', async () => {
  const calls=[];
  const replies=[response({csrfToken:'before'}),response({challenge_id:'id'}),response({csrfToken:'after',cabinet:'client'}),response(null,204)];
  const client=new ApiClient(async (url,options)=>{calls.push({url,...options});return replies.shift();},'https://studio.test');
  await client.request('auth/request-code/','POST',{phone:'+992000000001'});
  await client.request('auth/verify-code/','POST',{challenge_id:'id',code:'987654'});
  assert.equal(await client.request('auth/logout/','POST',{}),null);
  assert.equal(calls[0].url,'/api/auth/csrf/');
  assert.equal(calls[1].headers['X-CSRFToken'],'before');
  assert.equal(calls[3].headers['X-CSRFToken'],'after');
  assert.ok(calls.every(c=>c.credentials==='same-origin'&&c.cache==='no-store'));
  assert.deepEqual(JSON.parse(calls[1].body),{phone:'+992000000001'});
});

test('file requests preserve FormData and let the browser set its boundary', async () => {
  const dom=new JSDOM();
  try {
    const form=new dom.window.FormData();form.set('bio_ru','Описание');
    let captured;
    const client=new ApiClient(async(url,options)=>{captured=options;return response({});},'https://studio.test');
    client.csrfToken='token';
    await client.request('me/profile/','PATCH',form);
    assert.equal(captured.body,form);
    assert.equal(captured.headers['Content-Type'],undefined);
    assert.equal(captured.headers['X-CSRFToken'],'token');
  } finally {dom.window.close();}
});

test('conflicts are reported once; forbidden responses force a new CSRF request', async () => {
  const calls=[];
  const client=new ApiClient(async(url)=>{calls.push(url);return response({detail:'Conflict'},409);},'https://studio.test');
  client.csrfToken='old';
  await assert.rejects(client.request('bookings/id/','PATCH',{version:1}),e=>e instanceof ApiError&&e.status===409);
  assert.equal(calls.length,1,'mutations must never retry automatically');
  client.fetcher=async()=>response({},403);
  await assert.rejects(client.request('me/'),e=>e.status===403);
  assert.equal(client.csrfToken,null);
});

test('pagination accepts same-origin absolute links and rejects external or cyclic links', async () => {
  const client=new ApiClient(async url=>response(url.includes('page=2')?{results:[2],next:null}:{results:[1],next:'https://studio.test/api/bookings/?page=2'}),'https://studio.test');
  assert.deepEqual(await client.all('bookings/'),[1,2]);
  assert.throws(()=>client.url('https://other.test/api/bookings/'));
  assert.throws(()=>client.url('/private/'));
  client.fetcher=async()=>response({results:[],next:'/api/bookings/'});
  await assert.rejects(client.all('bookings/'),e=>e.status===503);
});

test('network and SMS failures never become successful responses', async () => {
  const client=new ApiClient(async()=>{throw new Error('offline');},'https://studio.test');
  await assert.rejects(client.request('catalog/'),e=>e.status===0);
  await assert.rejects(client.request('auth/request-code/','POST',{}),e=>e.status===0);
  client.csrfToken='csrf';client.fetcher=async()=>response({},503);
  await assert.rejects(client.request('auth/request-code/','POST',{}),e=>e.status===503);
});

test('premium gifts, integer-cent estimates and incompatible extras match booking rules', () => {
  const catalog=Object.entries({premium:10000,standard:4000,album:500,foteha_one:1000,foteha_two:1500,love_story:2000}).map(([code,price])=>({code,price}));
  assert.deepEqual(estimate(catalog,'wedding','premium',['album','foteha_one','love_story']),{total:12000,deposit:2400});
  assert.equal(estimate(catalog,'wedding','premium',['foteha_two']),null);
  assert.deepEqual(estimate(catalog,'wedding','standard',['album']),{total:4500,deposit:900});
});

test('Dushanbe inputs, server-adjusted countdown and fifteen-day cutoff are deterministic', () => {
  assert.equal(localInput('2027-06-20T08:00:00Z'),'2027-06-20T13:00');
  assert.equal(apiDateTime('2027-06-20T13:00'),'2027-06-20T13:00:00+05:00');
  assert.deepEqual(countdown('2027-06-20T08:00:00Z',5000,Date.parse('2027-06-19T07:59:55Z')),[1,0,0,0]);
  assert.deepEqual(countdown('2020-01-01T00:00:00Z'),[0,0,0,0]);
  const booking={status:'confirmed',date:'2027-06-20',shoot_start:'2027-06-20T08:00:00Z'};
  assert.equal(changeAllowed(booking,'2027-06-05'),true);
  assert.equal(changeAllowed(booking,'2027-06-06'),false);
  assert.equal(safeMedia('javascript:alert(1)','https://studio.test'),'');
});
