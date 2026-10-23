import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {createApplication} from '../static/studio/app.js';
import {ApiError} from '../static/studio/api.js';

const page = rows => ({count:rows.length,next:null,previous:null,results:rows});
const team=[1,2,3].map(id=>({id,slug:'person'+id,name:'Участник '+id,position_ru:'Оператор',position_tg:'Наворбардор',experience:id===3?null:3,bio_ru:'',bio_tg:'',photo:null}));
const catalog=Object.entries({standard:4000,pro:6000,premium:10000,foteha_one:1000,foteha_two:1500,love_story:2000,album:500,hall_screen:2000}).map(([code,price])=>({code,price:price.toFixed(2),revision:1,kind:['standard','pro','premium'].includes(code)?'package':'addon',title_ru:code,title_tg:code,active:true}));
const customer={id:10,cabinet:'client',role:'client',phone:'+992000000001',member:null};
const owner={id:20,cabinet:'management',role:'owner',phone:'+992000000002',member:team[0]};
const employee={id:30,cabinet:'employee',role:'employee',phone:'+992000000003',member:team[1]};
const order=(overrides={})=>({id:'00000000-0000-4000-8000-000000000001',event:'wedding',date:'2099-06-20',status:'new',wedding_time:null,shoot_start:null,shoot_end:null,location:'Зал',version:4,crew:[],client_name:'Клиент',client_note:'',quote:{package:'standard',extras:[],lines:[{title_ru:'Старая цена',title_tg:'Нархи пешина',price:'4000.00'}],total:'4000.00',deposit:'800.00'},total:'4000.00',paid_amount:'0.00',server_time:new Date().toISOString(),admin_note:'',change_requests:[],...overrides});

async function setup(t,{user=null,path='/',booking=order(),handler}={}) {
  const dom=new JSDOM('<!doctype html><html><body><header id="header"></header><main id="content"></main><footer id="navigation"></footer><div id="notice" hidden></div></body></html>',{url:'https://studio.test/#'+path});
  const {window}=dom;window.scrollTo=()=>{};window.confirm=()=>true;window.localStorage.setItem('creative-language','ru');
  let session=user;
  const calls=[];
  const api={async request(path,method='GET',body){
    calls.push({path,method,body});
    const override=await handler?.({path,method,body,calls});
    if(override!==undefined)return override;
    if(path==='me/'){if(!session)throw new ApiError(403,{});return structuredClone(session);}
    if(path==='auth/request-code/')return {challenge_id:'challenge-1',expires_in:300};
    if(path==='auth/verify-code/'){session=user||customer;return {...session,csrfToken:'rotated'};}
    if(path==='auth/logout/'){session=null;return null;}
    if(path==='catalog/')return structuredClone(catalog);
    if(path==='team/')return structuredClone(team);
    if(path.startsWith('faq/')||path.startsWith('reviews/'))return page([]);
    if(path==='portfolio/'||path.startsWith('portfolio/?'))return page([]);
    if(path.startsWith('management/availability/'))return team.map(p=>({member:p.id,name:p.name,busy:false,booking:null}));
    if(path==='management/bindings/')return [{member:1,phone:owner.phone}];
    if(path===`bookings/${booking.id}/`&&method==='GET')return structuredClone(booking);
    if(path==='bookings/'&&method==='POST')return {...booking,...body};
    if(path.startsWith('bookings/?'))return page([booking]);
    return {};
  }};
  const app=createApplication({document:window.document,window,api});
  t.after(()=>{app.destroy();window.close();});
  await app.start();
  const q=selector=>window.document.querySelector(selector);
  const fill=(form,name,value)=>{form.elements[name].value=value;form.elements[name].dispatchEvent(new window.Event('input',{bubbles:true}));};
  const change=(input,value)=>{if(input.type==='checkbox')input.checked=value;else input.value=value;input.dispatchEvent(new window.Event('change',{bubbles:true}));};
  const submit=async form=>{form.dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));await app.idle();};
  return {app,window,q,fill,change,submit,calls,api,booking};
}

test('homepage uses real catalog/team, empty media and escaped content',async t=>{
  const {q}=await setup(t,{handler:({path})=>path==='team/'?[{...team[0],name:'<img src=x onerror=alert(1)>'}]:undefined});
  assert.ok(q('h1.sr-only'));
  assert.equal(q('.person h3').textContent,'<img src=x onerror=alert(1)>');
  assert.equal(q('.person h3 img'),null);
  assert.equal(q('video'),null);
  assert.equal(q('#navigation').children.length,5);
  assert.equal(q('[data-action="switch-role"]'),null);
});

test('booking draft survives real phone challenge and only posts after explicit submission',async t=>{
  const {app,q,fill,change,submit,calls,window}=await setup(t,{path:'/booking'});
  let form=q('[data-form="booking"]');
  fill(form,'client_name','Фарид');fill(form,'date','2099-06-20');fill(form,'location','Наш зал');
  change(form.elements.package,'premium');
  assert.equal(form.querySelector('[name="extras"][value="album"]').disabled,true);
  assert.equal(form.querySelector('[name="extras"][value="foteha_two"]').disabled,true);
  change(form.querySelector('[name="extras"][value="love_story"]'),true);
  await submit(form);
  form=q('[data-form="request-code"]');fill(form,'phone',customer.phone);await submit(form);
  assert.ok(q('[data-action="resend"]').disabled);
  form=q('[data-form="verify"]');fill(form,'code','987654');await submit(form);
  assert.equal(window.location.hash,'#/booking');
  form=q('[data-form="booking"]');assert.equal(form.elements.client_name.value,'Фарид');
  assert.equal(calls.filter(c=>c.path==='bookings/'&&c.method==='POST').length,0);
  await submit(form);
  const payload=calls.find(c=>c.path==='bookings/'&&c.method==='POST').body;
  assert.deepEqual(payload,{event:'wedding',package:'premium',extras:['love_story'],client_name:'Фарид',date:'2099-06-20',location:'Наш зал',client_note:''});
  assert.equal(window.location.hash,'#/account/order/'+order().id);
  assert.ok(q('[data-form="change-request"]'));
  await app.navigate('/account');assert.ok(q('.book-card'));
});

test('unavailable SMS does not open verification or claim delivery',async t=>{
  const {q,fill,submit}=await setup(t,{path:'/account',handler:({path})=>{if(path==='auth/request-code/')throw new ApiError(503,{});}});
  const form=q('[data-form="request-code"]');fill(form,'phone',customer.phone);await submit(form);
  assert.equal(q('[data-form="verify"]'),null);
  assert.match(form.querySelector('[data-form-error]').textContent,/недоступен/);
  assert.equal(q('#notice').hidden,true);
});

test('failed booking remains editable and never shows success',async t=>{
  const {q,fill,submit,window}=await setup(t,{user:customer,path:'/booking',handler:({path,method})=>{if(path==='bookings/'&&method==='POST')throw new ApiError(400,{date:['Выберите другую дату.']});}});
  const form=q('[data-form="booking"]');fill(form,'client_name','Фарид');fill(form,'date','2099-06-20');await submit(form);
  assert.match(form.querySelector('[data-form-error]').textContent,/другую дату/);
  assert.equal(form.elements.client_name.value,'Фарид');
  assert.equal(window.location.hash,'#/booking');assert.equal(q('#notice').hidden,true);
});

test('manager account opens management and employee cannot open price tools',async t=>{
  const manager=await setup(t,{user:owner,path:'/account'});
  assert.equal(manager.window.location.hash,'#/management');
  assert.ok(manager.q('a[href="#/management/prices"]'));
  const staff=await setup(t,{user:employee,path:'/employee/prices'});
  assert.equal(staff.q('[data-form="prices"]'),null);
  assert.match(staff.q('#content').textContent,/Нет доступа/);
  await staff.app.navigate('/management');
  assert.equal(staff.q('[data-form="binding"]'),null);
});

test('client sees snapshot and live countdown; cancellation sends a request, not a status update',async t=>{
  const booking=order({status:'confirmed',shoot_start:'2099-06-20T08:00:00Z'});
  const {q,fill,change,submit,calls}=await setup(t,{user:customer,path:'/account/order/'+booking.id,booking});
  assert.match(q('#content').textContent,/Старая цена/);
  assert.ok(q('[data-countdown]').textContent.length>0);
  const form=q('[data-form="change-request"]');change(form.elements.kind,'cancel');fill(form,'reason','Просьба позвонить');await submit(form);
  const call=calls.find(c=>c.path.endsWith('/change-requests/'));
  assert.deepEqual(call.body,{kind:'cancel',reason:'Просьба позвонить'});
  assert.equal(calls.some(c=>c.method==='PATCH'),false);
});

test('busy operators are disabled; administrator saves with version without silently repricing',async t=>{
  const booking=order({crew:[{member:1,duty:'operator'}]});
  const {q,fill,submit,calls}=await setup(t,{user:owner,path:'/management/order/'+booking.id,booking,handler:({path})=>path.startsWith('management/availability/')?team.map(p=>({member:p.id,busy:p.id<3,booking:p.id===1?booking.id:'another-booking',name:p.name})):undefined});
  const form=q('[data-form="booking-edit"]');
  assert.equal(form.querySelector('[name="crew"][value="1"]').disabled,false,'own reservation is editable');
  assert.equal(form.querySelector('[name="crew"][value="2"]').disabled,true,'other booking cannot reuse employee');
  fill(form,'admin_note','Позвонить');await submit(form);
  assert.deepEqual(calls.find(c=>c.method==='PATCH').body,{version:4,admin_note:'Позвонить'});
});

test('stale booking conflict preserves edits for review',async t=>{
  const booking=order();
  const {q,fill,submit}=await setup(t,{user:owner,path:'/management/order/'+booking.id,booking,handler:({method})=>{if(method==='PATCH')throw new ApiError(409,{detail:'Заказ изменён другим администратором.'});}});
  const form=q('[data-form="booking-edit"]');fill(form,'admin_note','Не терять текст');await submit(form);
  assert.match(form.querySelector('[data-form-error]').textContent,/другим администратором/);
  assert.equal(form.elements.admin_note.value,'Не терять текст');
});

test('price edit sends only changed entries with catalog revisions',async t=>{
  const {q,fill,submit,calls}=await setup(t,{user:owner,path:'/management/prices'});
  const form=q('[data-form="prices"]');fill(form,'standard','4500');await submit(form);
  assert.deepEqual(calls.find(c=>c.path==='management/prices/'&&c.method==='PATCH').body,{items:[{code:'standard',price:'4500',revision:1}]});
});

test('terminal booking can record payment without resending immutable fields',async t=>{
  const booking=order({status:'ready'});
  const {q,fill,submit,calls}=await setup(t,{user:owner,path:'/management/order/'+booking.id,booking});
  const form=q('[data-form="booking-edit"]');assert.equal(form.elements.status,undefined);
  fill(form,'paid_amount','4000.00');await submit(form);
  assert.deepEqual(calls.find(c=>c.method==='PATCH').body,{version:4,paid_amount:'4000.00'});
});

test('standalone foteha requote never adds wedding extras',async t=>{
  const booking=order({event:'foteha',quote:{package:'foteha_one',extras:[],lines:[]}});
  const {q,change,submit,calls}=await setup(t,{user:owner,path:'/management/order/'+booking.id,booking});
  const form=q('[data-form="reprice"]');change(form.elements.package,'foteha_two');
  assert.equal(form.querySelector('[name="extras"]'),null);await submit(form);
  assert.deepEqual(calls.find(c=>c.method==='PATCH').body,{version:4,package:'foteha_two',extras:[]});
});

test('employee requests only own videos and sends profile as multipart',async t=>{
  const {app,q,fill,submit,calls}=await setup(t,{user:employee,path:'/employee/videos'});
  assert.ok(calls.some(c=>c.path==='portfolio/?page=1&author=2'));
  await app.navigate('/employee/profile');
  const form=q('[data-form="profile"]');fill(form,'bio_ru','Моя биография');await submit(form);
  const body=calls.find(c=>c.path==='me/profile/'&&c.method==='PATCH').body;
  assert.equal(body.get('bio_ru'),'Моя биография');
  assert.equal(body.has('member'),false);assert.equal(body.has('role'),false);
});

test('own phone binding cannot be edited in management interface',async t=>{
  const {q}=await setup(t,{user:owner,path:'/management/bindings'});
  const form=q('[data-form="binding"][data-member="1"]');
  assert.equal(form.elements.phone.readOnly,true);
  assert.equal(form.querySelector('[type="submit"]'),null);
});

test('video edit sends permission and metadata without choosing a different author',async t=>{
  const post={id:5,author:2,title_ru:'Ролик',title_tg:'Навор',event:'wedding',placement:'reels',permission_confirmed:true,video:'/media/film.mp4'};
  const {q,fill,submit,calls}=await setup(t,{user:employee,path:'/employee/videos?edit=5',handler:({path,method})=>path==='portfolio/5/'&&method==='GET'?post:undefined});
  const form=q('[data-form="video"]');fill(form,'title_ru','Новая история');await submit(form);
  const upload=calls.find(c=>c.path==='portfolio/5/'&&c.method==='PATCH');
  assert.equal(upload.body.get('title_ru'),'Новая история');
  assert.equal(upload.body.get('permission_confirmed'),'true');
  assert.equal(upload.body.has('author'),false);
  assert.equal(upload.body.has('video'),false,'edit keeps existing file unless a replacement is chosen');
});

test('availability retry preserves unsaved crew selection',async t=>{
  let loads=0;
  const booking=order({crew:[{member:1,duty:'operator'}]});
  const {q,change,app}=await setup(t,{user:owner,path:'/management/order/'+booking.id,booking,handler:({path})=>{
    if(path.startsWith('management/availability/')){loads++;if(loads===2)throw new ApiError(503,{});}
  }});
  const form=q('[data-form="booking-edit"]');
  change(form.querySelector('[name="crew"][value="3"]'),true);
  change(form.elements.date,'2099-06-21');await app.idle();
  assert.ok(q('[data-action="retry-crew"]'));
  q('[data-action="retry-crew"]').click();await app.idle();
  assert.equal(form.querySelector('[name="crew"][value="3"]').checked,true);
});

test('logout clears private UI and returns to phone login',async t=>{
  const {q,window,app,calls}=await setup(t,{user:owner,path:'/management/bindings'});
  q('[data-action="logout"]').click();await app.idle();
  assert.equal(window.location.hash,'#/account');
  assert.ok(q('[data-form="request-code"]'));
  assert.equal(q('[data-form="binding"]'),null);
  assert.ok(calls.some(c=>c.path==='auth/logout/'&&c.method==='POST'));
  assert.equal(window.localStorage.length,1,'only language preference is persisted');
});
