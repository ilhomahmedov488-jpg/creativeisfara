import {ApiClient, ApiError} from './api.js';
import {translate} from './i18n.js';
import {escapeHtml as esc, safeMedia, today, localInput, apiDateTime, manager, staff, countdown, estimate, changeAllowed, transitions, ZONE} from './domain.js';

export function createApplication({document, window, api = new ApiClient(window.fetch.bind(window), window.location.origin)}) {
  const content=document.getElementById('content');
  const header=document.getElementById('header');
  const navigation=document.getElementById('navigation');
  const notice=document.getElementById('notice');
  let language='tg';
  try { if (window.localStorage.getItem('creative-language')==='ru') language='ru'; } catch { /* storage may be disabled */ }
  const state={language,user:null,catalog:[],team:[],faq:[],reviews:[],sample:[],failures:[],orders:new Map(),
    draft:{event:'wedding',package:'standard',extras:[],client_name:'',date:'',location:'',client_note:''},
    challenge:null,afterLogin:null,epoch:0,lastHash:null,serverOffset:0,mutating:false};
  let activeRender=Promise.resolve(), pending=Promise.resolve(), toastTimer, interval;
  const t=key=>translate(key,state.language);
  const localized=(value,key)=>value?.[`${key}_${state.language}`] || value?.[`${key}_ru`] || value?.[`${key}_tg`] || '';
  const money=value=>`${new Intl.NumberFormat(state.language==='tg'?'tg-TJ':'ru-RU',{maximumFractionDigits:2}).format(Number(value))} TJS`;
  const dateText=value=>value?new Intl.DateTimeFormat(state.language==='tg'?'tg-TJ':'ru-RU',{timeZone:ZONE,day:'numeric',month:'long',year:'numeric'}).format(new Date(value.length===10?value+'T12:00:00+05:00':value)):'';
  const timeText=value=>value?new Intl.DateTimeFormat(state.language==='tg'?'tg-TJ':'ru-RU',{timeZone:ZONE,hour:'2-digit',minute:'2-digit'}).format(new Date(value)):'';
  const dashboard=()=>manager(state.user)?'/management':staff(state.user)?'/employee':'/account';
  const currentRoute=()=>new URL((window.location.hash.slice(1)||'/'), 'https://navigation.invalid');
  const attr=(condition,text)=>condition?text:'';
  const options=(values,current,label=v=>t(v))=>values.map(v=>`<option value="${esc(v)}" ${attr(String(v)===String(current),'selected')}>${esc(label(v))}</option>`).join('');
  const button=(label,action,extra='',kind='secondary')=>`<button type="button" class="btn ${kind}" data-action="${action}" ${extra}>${esc(label)}</button>`;
  const link=(label,path,kind='')=>`<a class="btn ${kind}" href="#${esc(path)}">${esc(label)}</a>`;
  const field=(label,name,value='',type='text',extra='')=>`<label class="field">${esc(label)}<input type="${type}" name="${name}" value="${esc(value)}" ${extra}></label>`;
  const area=(label,name,value='',extra='')=>`<label class="field">${esc(label)}<textarea name="${name}" ${extra}>${esc(value)}</textarea></label>`;
  const select=(label,name,values,current,extra='',labeler)=>`<label class="field">${esc(label)}<select name="${name}" ${extra}>${options(values,current,labeler)}</select></label>`;
  const check=(name,label,checked=false,extra='')=>`<label class="check"><input type="checkbox" name="${name}" ${attr(checked,'checked')} ${extra}><span>${esc(label)}</span></label>`;
  const errors=()=>'<div class="error" role="alert" data-form-error></div>';
  const submit=label=>`<button class="btn" type="submit">${esc(label)}</button>`;
  const empty=label=>`<div class="empty">${esc(label)}</div>`;
  const badge=status=>`<span class="pill ${esc(status)}">${esc(t(status))}</span>`;
  const nameFor=id=>state.team.find(p=>p.id===Number(id))?.name || '—';
  const meta=(label,value)=>`<div><dt>${esc(label)}</dt><dd>${esc(value || '—')}</dd></div>`;
  const image=(url,alt,extra='')=>safeMedia(url,window.location.origin)?`<img src="${esc(safeMedia(url,window.location.origin))}" alt="${esc(alt)}" ${extra}>`:'';
  const cached=order=>{const old=state.orders.get(order.id);if(!old||old.version<=order.version)state.orders.set(order.id,order);return order;};
  const formData=form=>new window.FormData(form);
  const get=(data,key)=>String(data.get(key)??'').trim();
  const serialForm=form=>Object.fromEntries([...formData(form)].filter(([,v])=>typeof v==='string'));
  const dutyLabel=value=>t(value==='reels'?'reelsDuty':value);
  const statusError=error=>t(error.status===409?'conflict':error.status===403?'forbidden':error.status===429?'rateLimit':error.status===400?'invalid':error.status===404?'notFound':error.status===503?'unavailable':'failed');
  function errorText(error) {
    const details=[];
    function flatten(value){if(typeof value==='string')details.push(value);else if(Array.isArray(value))value.forEach(flatten);else if(value&&typeof value==='object')Object.values(value).forEach(flatten);}
    if(error instanceof ApiError && [400,409].includes(error.status)) flatten(error.data);
    return [statusError(error),...new Set(details)].join('\n');
  }
  function toast(text){notice.textContent=text;notice.hidden=false;window.clearTimeout(toastTimer);toastTimer=window.setTimeout(()=>notice.hidden=true,5000);}
  function icon(name){const shapes={home:'<path d="m3 10 9-7 9 7v11H3z"/><path d="M9 21v-8h6v8"/>',works:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m10 9 5 3-5 3zM7 4v16M17 4v16"/>',prices:'<path d="M4 3h13l4 4v14H4zM8 8h6M8 12h9M8 16h5"/>',book:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 2v6M17 2v6M3 11h18m-11 4 2 2 4-4"/>',account:'<circle cx="12" cy="8" r="4"/><path d="M4 22v-3a8 8 0 0 1 16 0v3"/>'};return `<svg viewBox="0 0 24 24" aria-hidden="true">${shapes[name]}</svg>`;}
  function chrome() {
    document.documentElement.lang=state.language;
    document.title='Creative Studio';
    const route=currentRoute().pathname;
    header.innerHTML=`<a class="brand" href="#/" aria-label="Creative Studio">${image('/static/studio/logo.png','Creative Studio')}</a><div class="header-actions"><div class="language" role="group" aria-label="Language">${['tg','ru'].map(l=>`<button type="button" data-action="language" data-language="${l}" aria-pressed="${l===state.language}">${l==='tg'?'TJ':'RU'}</button>`).join('')}</div>${state.user?button(t('logout'),'logout','','small logout'):link(t('login'),'/account','secondary small')}</div>`;
    const privateRoute=['/account','/employee','/management'].some(p=>route.startsWith(p));
    navigation.innerHTML=[['home','/'],['works','/works'],['prices','/prices'],['book','/booking'],['account',dashboard()]].map(([name,path])=>`<a href="#${path}" ${attr(name==='account'?privateRoute:route===path,'aria-current="page"')}>${icon(name)}<span>${esc(t(name))}</span></a>`).join('');
  }
  function plans() {
    const packages=state.catalog.filter(p=>p.kind==='package');
    return packages.length?`<div class="grid three">${packages.map(p=>`<article class="panel plan ${esc(p.code)}"><span class="eyebrow">Creative Studio</span><h3>${esc(localized(p,'title'))}</h3><div class="price">${esc(money(p.price))}</div><p>${esc(t(p.code+'Crew'))}</p><ul><li>${esc(t(p.code==='premium'?'premiumStart':'earlyStart'))}</li><li>${esc(t('delivery'))}</li></ul>${link(t('choose'),'/booking?package='+p.code,'full')}</article>`).join('')}</div>`:empty(t('failed'));
  }
  function videoCard(post,controls=false) {
    const media=safeMedia(post.video,window.location.origin);
    return `<article class="panel video-card">${media?`<video class="video ${esc(post.placement)}" src="${esc(media)}" controls playsinline preload="metadata" aria-label="${esc(localized(post,'title'))}"></video>`:''}<h3>${esc(localized(post,'title'))}</h3><p class="help">${esc(nameFor(post.author))} · ${esc(t(post.event))}</p>${controls?`<div class="actions">${link(t('edit'),dashboard()+'/videos?edit='+post.id,'secondary small')}${button(t('remove'),'delete-video',`data-id="${post.id}"`,'danger small')}</div>`:''}</article>`;
  }
  function teamSection() {
    return `<section class="section"><div class="section-head"><div><h2>${esc(t('team'))}</h2><p class="help">${esc(t('teamSub'))}</p></div><div class="row">${button('‹','team-prev',`aria-label="${esc(t('previous'))}"`,'secondary small')}${button('›','team-next',`aria-label="${esc(t('next'))}"`,'secondary small')}</div></div><div class="team-track" id="team-track">${state.team.map(person=>`<article class="person"><div class="portrait">${person.photo?image(person.photo,person.name,'loading="lazy"'):`<span class="initials" aria-hidden="true">${esc(person.name.split(' ').slice(0,2).map(n=>n[0]).join(''))}</span>`}</div><div class="person-body"><h3>${esc(person.name)}</h3><p class="muted">${esc(localized(person,'position'))}</p>${person.experience===null?'':`<span class="pill">${person.experience} ${esc(t('years'))}</span>`}<p class="person-bio help">${esc(localized(person,'bio'))}</p></div></article>`).join('')||empty(t('noTeam'))}</div></section>`;
  }
  function homePage() {
    return `<section><div class="hero"><div class="scene" aria-hidden="true"><div class="camera"><span class="camera-grip"></span></div></div>${image('/static/studio/logo.png','CREATIVE studio','class="hero-logo"')}<h1 class="sr-only">Creative Studio</h1><p>${esc(t('tagline'))}</p><div class="actions">${link(t('bookNow'),'/booking')}${link(t('seeWorks'),'/works','secondary')}</div></div><section class="section"><div class="section-head"><div><h2>${esc(t('portfolio'))}</h2></div>${link(t('all'),'/works','quiet')}</div>${state.sample.length?`<div class="grid three">${state.sample.slice(0,3).map(p=>videoCard(p)).join('')}</div>`:empty(t('noVideos'))}</section><section class="section"><h2>${esc(t('packages'))}</h2><p class="muted">${esc(t('packagesSub'))}</p>${plans()}</section>${teamSection()}<section class="section"><h2>${esc(t('process'))}</h2><ol class="process">${[1,2,3,4].map(n=>`<li>${esc(t('process'+n))}</li>`).join('')}</ol></section><section class="section"><h2>${esc(t('reviews'))}</h2>${state.reviews.length?`<div class="grid two">${state.reviews.slice(0,4).map(r=>`<blockquote class="panel review"><p>${esc(localized(r,'text'))}</p><cite>${esc(r.author_name)}</cite></blockquote>`).join('')}</div>`:empty(t('noReviews'))}</section><section class="section compact"><h2>${esc(t('faq'))}</h2>${state.faq.map(f=>`<details><summary>${esc(localized(f,'question'))}</summary><p>${esc(localized(f,'answer'))}</p></details>`).join('')}</section><section class="section panel soft"><h2>${esc(t('contact'))}</h2><div class="actions"><a class="btn secondary" href="tel:+992926112233">+992 926 11 22 33</a><a class="btn secondary" href="tel:+992982263030">+992 98 226 30 30</a></div></section></section>`;
  }
  function packageValues(event) {return event==='wedding'?['standard','pro','premium']:event==='foteha'?['foteha_one','foteha_two']:['love_story'];}
  function extraChoices(packageCode,selected=[]) {
    const premium=packageCode==='premium';
    return `<fieldset><legend>${esc(t('extras'))}</legend>${['foteha_one','foteha_two','love_story','album','hall_screen'].map(code=>{
      const item=state.catalog.find(p=>p.code===code);if(!item)return '';
      const included=premium&&['album','foteha_one'].includes(code),blocked=premium&&code==='foteha_two';
      return check('extras',`${localized(item,'title')} · ${included?t('included'):money(item.price)}`,included||selected.includes(code),`value="${code}" ${attr(included||blocked,'disabled')}`);
    }).join('')}${premium?`<p class="help">${esc(t('premiumUpgrade'))}</p>`:''}</fieldset>`;
  }
  function bookingPage(route) {
    const chosen=route.searchParams.get('package');
    if(chosen&&['standard','pro','premium'].includes(chosen)){state.draft.event='wedding';state.draft.package=chosen;}
    const d=state.draft;
    if(!packageValues(d.event).includes(d.package))d.package=packageValues(d.event)[0];
    return `<section class="compact"><h1>${esc(t('bookingTitle'))}</h1><p class="muted">${esc(t('bookingSub'))}</p>${staff(state.user)||manager(state.user)?`<div class="panel">${esc(t('teamBooking'))}<div class="actions">${link(t('account'),dashboard())}</div></div>`:`<form data-form="booking" class="panel stack">${select(t('event'),'event',['wedding','love_story','foteha'],d.event)}<div id="booking-package">${select(t('package'),'package',packageValues(d.event),d.package)}</div>${field(t('name'),'client_name',d.client_name,'text','required maxlength="150" autocomplete="name"')}${field(t('date'),'date',d.date,'date',`required min="${today()}"`)}${field(t('location'),'location',d.location,'text','maxlength="250"')}${area(t('note'),'client_note',d.client_note,'maxlength="5000"')}<div id="booking-extras">${d.event==='wedding'?extraChoices(d.package,d.extras):''}</div><div class="panel soft" id="booking-estimate"></div><p class="help">${esc(t('basePrice'))} ${esc(t('transport'))}</p><p class="help">${esc(t('offlinePay'))}</p>${!state.user?`<p>${esc(t('signToBook'))}</p>`:''}${errors()}${submit(state.user?t('send'):t('login'))}</form>`}</section>`;
  }
  function captureBooking(form) {
    if(!form)return;
    const data=serialForm(form);state.draft={...state.draft,...data,extras:[...formData(form).getAll('extras')].map(String)};
  }
  function updateEstimate() {
    const target=document.getElementById('booking-estimate');if(!target)return;
    const d=state.draft,quote=estimate(state.catalog,d.event,d.package,d.extras);
    target.innerHTML=quote?`<div class="money-lines"><div><span>${esc(t('estimate'))}</span><strong>${esc(money(quote.total))}</strong></div><div><span>${esc(t('deposit'))}</span><strong>${esc(money(quote.deposit))}</strong></div></div>`:esc(t('failed'));
  }
  function loginPage() {
    const c=state.challenge;
    return `<section class="compact"><div class="panel"><h1>${esc(t('login'))}</h1><p class="muted">${esc(t('loginSub'))}</p>${c?`<p>${esc(c.phone)}</p><p class="help">${esc(t('codeSent'))}</p><form data-form="verify" class="stack">${field(t('code'),'code','','text','required inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="one-time-code"')}${errors()}${submit(t('verify'))}</form><div class="actions">${button(t('resend'),'resend','id="resend-code"')}${button(t('changePhone'),'change-phone','','quiet')}</div><p class="help" id="code-expiry"></p>`:`<form data-form="request-code" class="stack">${field(t('phone'),'phone','','tel','required autocomplete="tel" placeholder="+992 …" maxlength="30"')}${errors()}${submit(t('getCode'))}</form>`}</div></section>`;
  }
  function updateClocks() {
    document.querySelectorAll('[data-countdown]').forEach(el=>{
      const [d,h,m,s]=countdown(el.dataset.countdown,state.serverOffset);
      el.textContent=`${d} ${t('days')} · ${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    });
    const c=state.challenge, resend=document.getElementById('resend-code'),expiry=document.getElementById('code-expiry');
    if(c&&resend){const wait=Math.max(0,Math.ceil((c.resendAt-Date.now())/1000));resend.disabled=wait>0||state.mutating;resend.textContent=wait?`${t('resend')} · ${wait} ${t('seconds')}`:t('resend');if(expiry)expiry.textContent=Date.now()>=c.expiresAt?t('expired'):'';}
  }
  function pager(data,route) {
    if(!data.next&&!data.previous)return '';
    const page=Number(route.searchParams.get('page')||1);
    const path=n=>{const search=new URLSearchParams(route.search);search.set('page',n);return route.pathname+'?'+search;};
    return `<div class="pagination">${data.previous?link(t('previous'),path(page-1),'secondary small'):''}<span>${page}</span>${data.next?link(t('next'),path(page+1),'secondary small'):''}</div>`;
  }
  async function bookingList(route,internal=false) {
    const selected=route.searchParams.get('date')||'';
    const params=new URLSearchParams({page:route.searchParams.get('page')||'1'});if(selected)params.set('date',selected);
    const data=await api.request('bookings/?'+params);
    const prefix=internal?dashboard():'/account';
    return `${internal?'':`<div class="section-head"><h1>${esc(t('orders'))}</h1>${link(t('book'),'/booking','secondary')}</div>`}<form data-form="date-filter" class="row" data-path="${esc(route.pathname)}">${field(t('date'),'date',selected,'date')}${submit(t('refresh'))}${selected?link(t('all'),route.pathname,'quiet'):''}</form><div class="stack section">${data.results.map(o=>{cached(o);return `<a class="book-card" href="#${prefix}/order/${o.id}"><div class="row between">${badge(o.status)}<span class="help">#${esc(o.id.slice(0,8))}</span></div><h3>${esc(t(o.event))} · ${esc(dateText(o.date))}</h3><p>${esc(o.location)}</p>${o.shoot_start?`<p>${esc(t('shootStart'))}: ${esc(timeText(o.shoot_start))}</p>`:''}${o.total!==undefined?`<p>${esc(money(o.total))}${manager(state.user)?` · ${esc(o.client_name)}`:''}</p>`:''}</a>`;}).join('')||empty(t('noOrders'))}</div>${pager(data,route)}`;
  }
  function accountShell(active,body) {
    const base=dashboard(),full=manager(state.user),member=state.user.member;
    const tabs=full?[['bookings',''],['availability','/availability'],['prices','/prices'],['videos','/videos'],['profile','/profile'],['bindings','/bindings'],['content','/content/reviews']]:[['myWork',''],['videos','/videos'],['profile','/profile']];
    return `<section><div class="account-heading"><div><span class="eyebrow">Creative Studio</span><h1>${esc(t(full?'management':'account'))}</h1><p class="muted">${esc(member?.name||state.user.phone)}</p></div>${button(t('logout'),'logout','','secondary small')}</div><nav class="tabs" aria-label="${esc(t('account'))}">${tabs.map(([label,path])=>`<a href="#${base}${path}" ${attr(label===active,'aria-current="page"')}>${esc(t(label))}</a>`).join('')}</nav>${body}</section>`;
  }
  function orderSummary(o) {
    const financial=o.total!==undefined;
    if(o.server_time)state.serverOffset=new Date(o.server_time).getTime()-Date.now();
    return `<div class="section-head"><div><p class="eyebrow">#${esc(o.id.slice(0,8))}</p><h1>${esc(t(o.event))}</h1>${badge(o.status)}</div>${button(t('refresh'),'refresh','','secondary small')}</div><div class="grid two"><div class="panel"><dl class="metadata">${meta(t('date'),dateText(o.date))}${meta(t('location'),o.location)}${meta(t('shootStart'),o.shoot_start?`${dateText(o.shoot_start)} · ${timeText(o.shoot_start)}`:t('pendingTime'))}${o.shoot_end?meta(t('shootEnd'),`${dateText(o.shoot_end)} · ${timeText(o.shoot_end)}`):''}${o.client_name?meta(t('client'),o.client_name):''}${o.client_phone?meta(t('phone'),o.client_phone):''}${o.client_note?meta(t('clientNote'),o.client_note):''}</dl>${o.crew.length?`<h3>${esc(t('crew'))}</h3>${o.crew.map(c=>`<p class="help">${esc(nameFor(c.member))} · ${esc(dutyLabel(c.duty))}</p>`).join('')}`:''}</div><div class="stack">${o.status==='confirmed'&&o.shoot_start?`<div class="countdown"><div class="countdown-label">${esc(t('untilShoot'))}</div><div class="digits" data-countdown="${esc(o.shoot_start)}"></div></div>`:''}${financial?`<div class="panel money-lines">${(o.quote?.lines||[]).map(line=>`<div><span>${esc(localized(line,'title'))}${line.included?` · ${esc(t('included'))}`:''}</span><strong>${esc(money(line.price))}</strong></div>`).join('')}${o.quote?.adjustment?`<div><span>${esc(o.quote.adjustment.reason)}</span><strong>${esc(money(o.quote.adjustment.amount))}</strong></div>`:''}<hr class="divider"><div><span>${esc(t('total'))}</span><strong>${esc(money(o.total))}</strong></div><div><span>${esc(t('deposit'))}</span><strong>${esc(money(o.quote?.deposit||0))}</strong></div><div><span>${esc(t('paid'))}</span><strong>${esc(money(o.paid_amount))}</strong></div><div><span>${esc(t('balance'))}</span><strong>${esc(money(Number(o.total)-Number(o.paid_amount)))}</strong></div><p class="help">${esc(t('offlinePay'))}</p></div>`:''}</div></div>`;
  }
  function clientChanges(o) {
    const pendingChange=o.change_requests?.some(c=>c.state==='pending');
    const history=(o.change_requests||[]).map(c=>`<div class="panel"><div class="row between"><strong>${esc(t(c.kind==='cancel'?'cancel':'reschedule'))}</strong>${badge(c.state)}</div><p>${esc(c.reason)}</p>${c.requested_date?`<p>${esc(dateText(c.requested_date))}${c.requested_time?' · '+esc(c.requested_time):''}</p>`:''}${c.decision_note?`<p class="help">${esc(c.decision_note)}</p>`:''}</div>`).join('');
    return `<section class="section compact"><h2>${esc(t('changeRequests'))}</h2><div class="stack">${history}</div><p class="help">${esc(t('changePolicy'))}</p>${pendingChange?`<p>${esc(t('pendingChange'))}</p>`:['new','confirmed'].includes(o.status)?`<form data-form="change-request" data-id="${o.id}" class="panel stack">${select(t('changeRequests'),'kind',changeAllowed(o)?['reschedule','cancel']:['cancel'],changeAllowed(o)?'reschedule':'cancel','',v=>t(v==='cancel'?'cancel':'reschedule'))}<div data-reschedule-fields>${field(t('requestedDate'),'requested_date','','date',`min="${today()}"`)}${field(t('requestedTime')+' · '+t('optional'),'requested_time','','time')}</div>${area(t('reason'),'reason','','required maxlength="3000"')}${errors()}${submit(t('send'))}</form>`:''}</section>`;
  }
  async function publicWorks(route) {
    const filters=new URLSearchParams({page:route.searchParams.get('page')||'1'});
    for(const key of ['event','placement'])if(route.searchParams.get(key))filters.set(key,route.searchParams.get(key));
    const data=await api.request('portfolio/?'+filters);
    return `<section><h1>${esc(t('portfolio'))}</h1><form data-form="works-filter" class="grid two">${select(t('event'),'event',['','wedding','love_story','foteha'],route.searchParams.get('event')||'','',v=>v?t(v):t('all'))}${select(t('placement'),'placement',['','portfolio','reels'],route.searchParams.get('placement')||'','',v=>v?t(v==='portfolio'?'portfolio':'reels'):t('all'))}${submit(t('refresh'))}</form><div class="grid three section">${data.results.map(p=>videoCard(p)).join('')||empty(t('noVideos'))}</div>${pager(data,route)}</section>`;
  }
  function crewMarkup(o,rows) {
    return state.team.map(person=>{
      const assignment=o.crew.find(c=>c.member===person.id),availability=rows?.find(r=>r.member===person.id);
      const busy=availability?.busy&&availability.booking!==o.id;
      const own=availability?.busy&&availability.booking===o.id;
      return `<div class="crew-row"><label class="check"><input type="checkbox" name="crew" value="${person.id}" ${attr(assignment,'checked')} ${attr(busy&&!assignment,'disabled')} data-conflict="${!!busy}"><span>${esc(person.name)}<span class="crew-status ${busy?'busy':''}">${esc(t(busy?'busy':own?'ownReservation':'free'))}${busy?` · #${esc(availability.booking.slice(0,8))}`:''}</span></span></label><select name="duty-${person.id}" aria-label="${esc(t('crew')+' · '+person.name)}" ${attr(!assignment,'disabled')}>${options(['operator','photographer','reels','assistant'],assignment?.duty||'operator',dutyLabel)}</select></div>`;
    }).join('');
  }
  async function loadCrew(form,o,day) {
    const target=form.querySelector('[data-crew]');if(!target)return;
    const sequence=(Number(form.dataset.crewSequence)||0)+1;form.dataset.crewSequence=sequence;
    const controls=[...target.querySelectorAll('input[name="crew"]')];
    if(controls.length)form.crewDraft=controls.filter(input=>input.checked).map(input=>({member:Number(input.value),duty:form.elements['duty-'+input.value].value}));
    target.dataset.ready='false';
    try {
      const rows=await api.request('management/availability/?date='+encodeURIComponent(day));
      if(!form.isConnected||form.dataset.crewSequence!==String(sequence))return;
      const current=form.crewDraft?{...o,crew:form.crewDraft}:o;
      target.innerHTML=crewMarkup(current,rows);target.dataset.ready='true';target.dataset.readyOnce='true';
    } catch(error) {
      if(form.isConnected&&form.dataset.crewSequence===String(sequence))target.innerHTML=`<p class="error">${esc(t('noAvailability'))}</p>${button(t('retry'),'retry-crew')}`;
    }
  }
  function readCrew(form) {
    const target=form.querySelector('[data-crew]');
    if(target?.dataset.ready!=='true')throw new ApiError(503,{});
    const inputs=[...form.querySelectorAll('input[name="crew"]:checked')];
    if(inputs.some(input=>input.dataset.conflict==='true'))throw new ApiError(409,{});
    return inputs.map(input=>({member:Number(input.value),duty:form.elements['duty-'+input.value].value}));
  }
  function managerEdit(o) {
    const terminal=['ready','cancelled'].includes(o.status);
    return `<section class="section"><h2>${esc(t('edit'))}</h2><form data-form="booking-edit" data-id="${o.id}" class="panel stack"><div class="grid two">${terminal?'':`${field(t('date'),'date',o.date,'date','required')}${select(t('status'),'status',transitions[o.status],o.status)}${o.event==='wedding'?field(t('weddingTime'),'wedding_time',o.wedding_time?.slice(0,5)||'','time'):`${field(t('shootStart'),'shoot_start',localInput(o.shoot_start),'datetime-local')}${field(t('shootEnd')+' · '+t('optional'),'shoot_end',localInput(o.shoot_end),'datetime-local')}`}${field(t('location'),'location',o.location,'text','maxlength="250"')}`}${field(t('paid'),'paid_amount',o.paid_amount,'number',`required min="0" max="${esc(o.total)}" step="0.01"`)}</div>${area(t('adminNote'),'admin_note',o.admin_note||'','maxlength="5000"')}${terminal?'':`<fieldset><legend>${esc(t('crew'))}</legend><div data-crew data-ready="false">${esc(t('loading'))}</div></fieldset>`}${errors()}${submit(t('save'))}</form>${o.status==='new'?`<details class="panel section"><summary>${esc(t('reprice'))}</summary><p class="help">${esc(t('repricePolicy'))}</p><form data-form="reprice" data-id="${o.id}" class="stack">${select(t('package'),'package',packageValues(o.event),o.quote.package)}<div data-quote-extras>${o.event==='wedding'?extraChoices(o.quote.package,o.quote.extras):''}</div>${errors()}${submit(t('reprice'))}</form><hr class="divider"><form data-form="adjustment" data-id="${o.id}" class="stack">${field(t('adjustment'),'adjustment',o.quote.adjustment?.amount||'0.00','number','required step="0.01"')}${area(t('adjustmentReason'),'adjustment_reason',o.quote.adjustment?.reason||'','required maxlength="1000"')}${errors()}${submit(t('save'))}</form></details>`:''}</section>`;
  }
  function managerChanges(o) {
    return `<section class="section"><h2>${esc(t('changeRequests'))}</h2><div class="stack">${(o.change_requests||[]).map(c=>`<article class="panel"><div class="row between"><h3>${esc(t(c.kind==='cancel'?'cancel':'reschedule'))}</h3>${badge(c.state)}</div><p class="readonly">${esc(c.reason)}</p>${c.requested_date?`<p>${esc(dateText(c.requested_date))} ${esc(c.requested_time||'')}</p>`:''}${c.decision_note?`<p class="help">${esc(c.decision_note)}</p>`:''}${c.state==='pending'?`<form data-form="decision" data-id="${o.id}" data-change="${c.id}" data-kind="${c.kind}" data-date="${c.requested_date||o.date}" class="stack">${c.kind==='cancel'?`<p class="help">${esc(t('cancelCall'))}</p>`:''}${select(t('decision'),'approve',['','yes','no'],'','required',v=>v==='yes'?t('approve'):v==='no'?t('reject'):t('choose'))}${area(t('note'),'note','','maxlength="3000"')}${c.kind==='reschedule'?`<fieldset><legend>${esc(t('crew'))}</legend><div data-crew data-ready="false">${esc(t('loading'))}</div></fieldset>`:''}${errors()}${submit(t('decide'))}</form>`:''}</article>`).join('')||empty(t('noData'))}</div></section>`;
  }
  async function orderPage(route) {
    const id=route.pathname.split('/')[3];
    const o=cached(await api.request(`bookings/${encodeURIComponent(id)}/`));
    const full=manager(state.user),employee=staff(state.user)&&!full;
    return `<section>${link(t('back'),dashboard(),'quiet')}${orderSummary(o)}${full?managerEdit(o)+managerChanges(o):employee?'':clientChanges(o)}</section>`;
  }
  async function availabilityPage(route) {
    const day=route.searchParams.get('date')||today();
    const rows=await api.request('management/availability/?date='+encodeURIComponent(day));
    return `<h2>${esc(t('availability'))}</h2><form data-form="date-filter" class="row" data-path="/management/availability">${field(t('date'),'date',day,'date','required')}${submit(t('refresh'))}</form><div class="grid three section">${rows.map(p=>`<article class="panel"><div class="row between"><h3>${esc(p.name)}</h3>${badge(p.busy?'busy':'free')}</div>${p.booking?link('#'+p.booking.slice(0,8),'/management/order/'+p.booking,'quiet'):''}</article>`).join('')}</div>`;
  }
  function pricesEditor() {
    return `<h2>${esc(t('priceEdit'))}</h2><p class="muted">${esc(t('pricePolicy'))}</p><form data-form="prices" class="panel">${state.catalog.map(item=>`<label class="price-row"><span>${esc(localized(item,'title'))} <small>TJS</small></span><input name="${esc(item.code)}" type="number" value="${esc(item.price)}" step="0.01" min="0" required aria-label="${esc(localized(item,'title'))}"></label>`).join('')}${errors()}<div class="actions">${submit(t('save'))}</div></form>`;
  }
  async function bindingsPage() {
    const rows=await api.request('management/bindings/');
    return `<h2>${esc(t('bindings'))}</h2><p class="help">${esc(t('bindingPolicy'))}</p><div class="panel">${state.team.map(person=>{const own=person.id===state.user.member?.id,phone=rows.find(r=>r.member===person.id)?.phone||'';return `<article class="binding-row"><h3>${esc(person.name)}</h3><form data-form="binding" data-member="${person.id}"><div class="row">${field(t('phone'),'phone',phone,'tel',`required maxlength="30" autocomplete="off" ${attr(own,'readonly')}`)}${!own?`${submit(t('save'))}${phone?button(t('unbind'),'unbind',`data-member="${person.id}"`,'danger small'):''}`:''}</div>${errors()}</form></article>`;}).join('')}</div>`;
  }
  function profilePage() {
    const p=state.user.member;
    if(!p)return empty(t('noData'));
    return `<div class="compact"><h2>${esc(t('profile'))}</h2><div class="panel"><h3>${esc(p.name)}</h3><p>${esc(localized(p,'position'))}</p><form data-form="profile" class="stack">${area(t('bioRu'),'bio_ru',p.bio_ru,'maxlength="5000"')}${area(t('bioTg'),'bio_tg',p.bio_tg,'maxlength="5000"')}${p.photo?`<div class="portrait">${image(p.photo,p.name)}</div>`:''}${field(t('photo'),'photo','','file','accept="image/jpeg,image/png,image/webp"')}<p class="help">${esc(t('photoHelp'))}</p>${errors()}${submit(t('save'))}</form></div></div>`;
  }
  async function videosPage(route) {
    const full=manager(state.user),member=state.user.member;
    const params=new URLSearchParams({page:route.searchParams.get('page')||'1'});
    if(!full)params.set('author',member.id);
    const posts=await api.request('portfolio/?'+params);
    const editId=route.searchParams.get('edit');
    let edit=null;
    if(editId){edit=await api.request('portfolio/'+encodeURIComponent(editId)+'/');if(!full&&edit.author!==member.id)throw new ApiError(403,{});}
    return `<h2>${esc(t('videos'))}</h2>${member?`<div class="panel compact"><h3>${esc(t(edit?'edit':'upload'))}</h3><p class="help">${esc(t('videoHelp'))}</p><form data-form="video" data-id="${edit?.id||''}" class="stack">${field(t('titleRu'),'title_ru',edit?.title_ru||'','text','required maxlength="180"')}${field(t('titleTg'),'title_tg',edit?.title_tg||'','text','required maxlength="180"')}${select(t('event'),'event',['wedding','love_story','foteha'],edit?.event||'wedding')}${select(t('placement'),'placement',['reels','portfolio'],edit?.placement||'reels','',v=>t(v==='portfolio'?'portfolio':'reels'))}${field(t('videoFile'),'video','','file',`accept="video/mp4,video/webm" ${attr(!edit,'required')}`)}${edit?`<p class="help">${esc(t('chooseFile'))}</p>`:''}${check('permission_confirmed',t('consent'),edit?.permission_confirmed||false,'required')}${errors()}${submit(t(edit?'save':'upload'))}</form></div>`:''}<div class="grid three section">${posts.results.map(p=>videoCard(p,true)).join('')||empty(t('noVideos'))}</div>${pager(posts,route)}`;
  }
  async function contentPage(route) {
    const kind=route.pathname.endsWith('/faq')?'faq':'reviews',isFaq=kind==='faq';
    const rows=await api.request(kind+'/?page='+(route.searchParams.get('page')||'1'));
    const id=route.searchParams.get('edit'),item=id?await api.request(kind+'/'+encodeURIComponent(id)+'/'):{};
    return `<div class="tabs">${link(t('reviews'),'/management/content/reviews','secondary')}${link(t('faq'),'/management/content/faq','secondary')}</div><div class="panel compact"><h2>${esc(t(id?'edit':isFaq?'addFaq':'addReview'))}</h2><form data-form="content" data-kind="${kind}" data-id="${item.id||''}" class="stack">${isFaq?`${field(t('questionRu'),'question_ru',item.question_ru||'','text','required maxlength="250"')}${field(t('questionTg'),'question_tg',item.question_tg||'','text','required maxlength="250"')}${area(t('answerRu'),'answer_ru',item.answer_ru||'','required')}${area(t('answerTg'),'answer_tg',item.answer_tg||'','required')}${field(t('sort'),'order',item.order||0,'number','required min="0"')}`:`${field(t('author'),'author_name',item.author_name||'','text','required maxlength="150"')}${area(t('textRu'),'text_ru',item.text_ru||'','required')}${area(t('textTg'),'text_tg',item.text_tg||'','required')}${check('consent',t('consent'),item.consent||false)}${check('published',t('publish'),item.published||false)}`}${errors()}${submit(t('save'))}</form></div><div class="stack section">${rows.results.map(item=>`<article class="panel"><h3>${esc(isFaq?localized(item,'question'):item.author_name)}</h3><p class="readonly">${esc(localized(item,isFaq?'answer':'text'))}</p>${!isFaq?`<span class="pill">${esc(t(item.published?'publish':'pending'))}</span>`:''}<div class="actions">${link(t('edit'),'/management/content/'+kind+'?edit='+item.id,'secondary small')}${button(t('remove'),'delete-content',`data-kind="${kind}" data-id="${item.id}"`,'danger small')}</div></article>`).join('')||empty(t('noData'))}</div>${pager(rows,route)}`;
  }
  async function pageFor(route) {
    const path=route.pathname;
    if(path==='/')return homePage();
    if(path==='/prices')return `<section><h1>${esc(t('packages'))}</h1><p class="muted">${esc(t('packagesSub'))}</p>${plans()}<section class="section panel"><h2>${esc(t('extras'))}</h2><dl class="money-lines">${state.catalog.filter(p=>p.kind==='addon').map(p=>`<div><dt>${esc(localized(p,'title'))}</dt><dd>${esc(money(p.price))}</dd></div>`).join('')}</dl><p class="help">${esc(t('transport'))} ${esc(t('basePrice'))}</p></section></section>`;
    if(path==='/works')return publicWorks(route);
    if(path==='/booking')return bookingPage(route);
    if(['/account','/management','/employee'].some(p=>path===p||path.startsWith(p+'/'))) {
      try {state.user=await api.request('me/');}catch(error){if(error.status!==403)throw error;state.user=null;}
      chrome();
      if(!state.user){state.afterLogin=path==='/account'?state.afterLogin:path+route.search;return loginPage();}
      if(path.startsWith('/management')&&!manager(state.user))throw new ApiError(403,{});
      if(path.startsWith('/employee')&&!staff(state.user)&&!manager(state.user))throw new ApiError(403,{});
      if(path.includes('/order/'))return orderPage(route);
      if(path==='/account'&&(staff(state.user)||manager(state.user))){window.history.replaceState(null,'','#'+dashboard());return pageFor(currentRoute());}
      if(path==='/account')return bookingList(route);
      const section=path.split('/')[2]||'';
      if(section&&!staff(state.user)&&!manager(state.user))throw new ApiError(403,{});
      if(['availability','prices','bindings','content'].includes(section)&&!manager(state.user))throw new ApiError(403,{});
      let body,active;
      if(section==='availability'){body=await availabilityPage(route);active='availability';}
      else if(section==='prices'){state.catalog=await api.request('catalog/');body=pricesEditor();active='prices';}
      else if(section==='bindings'){body=await bindingsPage();active='bindings';}
      else if(section==='videos'){body=await videosPage(route);active='videos';}
      else if(section==='profile'){body=profilePage();active='profile';}
      else if(section==='content'){body=await contentPage(route);active='content';}
      else if(!section){body=await bookingList(route,true);active=manager(state.user)?'bookings':'myWork';}
      else throw new ApiError(404,{});
      return accountShell(active,body);
    }
    throw new ApiError(404,{});
  }
  async function hydrate() {
    updateEstimate();updateClocks();
    const changeForm=content.querySelector('[data-form="change-request"]');if(changeForm)updateChangeFields(changeForm);
    for(const form of content.querySelectorAll('[data-form="booking-edit"], [data-form="decision"]')){
      const o=state.orders.get(form.dataset.id);
      if(form.querySelector('[data-crew]'))await loadCrew(form,o,form.dataset.date||o.date);
    }
  }
  function render(force=false) {
    const hash=window.location.hash||'#/';
    if(!force&&state.lastHash===hash)return activeRender;
    state.lastHash=hash;
    const epoch=++state.epoch;
    activeRender=(async()=>{
      chrome();content.setAttribute('aria-busy','true');content.innerHTML=`<div class="loading" role="status">${esc(t('loading'))}</div>`;
      try {
        const html=await pageFor(currentRoute());
        if(epoch!==state.epoch)return;
        const warning=state.failures.length?`<div class="error-box"><p>${esc(t('failed'))}</p>${button(t('retry'),'reload-data')}</div>`:'';
        content.innerHTML=warning+html;
        content.setAttribute('aria-busy','false');chrome();await hydrate();
      }catch(error){if(epoch!==state.epoch)return;content.setAttribute('aria-busy','false');content.innerHTML=`<div class="error-box" role="alert"><p>${esc(errorText(error))}</p>${button(t('retry'),'refresh')}${link(t('home'),'/','secondary')}</div>`;}
    })();
    return activeRender;
  }
  function navigate(path) {window.history.pushState(null,'','#'+path);window.scrollTo?.({top:0,behavior:'instant'});return render(true);}
  async function loadPublic() {
    state.failures=[];
    const resources=[['catalog','catalog/'],['team','team/'],['faq','faq/'],['reviews','reviews/'],['sample','portfolio/']];
    await Promise.all(resources.map(async([key,path])=>{
      try {const result=await api.request(path);state[key]=Array.isArray(result)?result:result.results;if(key==='reviews')state[key]=state[key].filter(r=>r.published&&r.consent);}
      catch{state[key]=[];state.failures.push(key);}
    }));
  }
  function updateChangeFields(form) {
    const show=form.elements.kind.value==='reschedule';
    const group=form.querySelector('[data-reschedule-fields]');group.hidden=!show;
    group.querySelectorAll('input').forEach(input=>input.disabled=!show);
    form.elements.requested_date.required=show;
  }
  function changedPayload(form,o) {
    const data=serialForm(form),payload={version:o.version};
    for(const key of ['paid_amount','admin_note'])if(data[key]!==String(o[key]??''))payload[key]=data[key];
    if(!['ready','cancelled'].includes(o.status)){
      for(const key of ['date','status','location'])if(data[key]!==String(o[key]??''))payload[key]=data[key];
      if(o.event==='wedding'){const value=data.wedding_time||null;if(value!==(o.wedding_time?.slice(0,5)||null))payload.wedding_time=value;}
      else for(const key of ['shoot_start','shoot_end'])if(data[key]!==localInput(o[key]))payload[key]=apiDateTime(data[key]);
      const crew=readCrew(form);
      const normalized=rows=>JSON.stringify([...rows].sort((a,b)=>a.member-b.member));
      if(normalized(crew)!==normalized(o.crew))payload.crew=crew;
    }
    return payload;
  }
  async function sendCode(phone) {
    const result=await api.request('auth/request-code/','POST',{phone});
    state.challenge={id:result.challenge_id,phone,resendAt:Date.now()+60000,expiresAt:Date.now()+result.expires_in*1000};
    await render(true);toast(t('codeSent'));
  }
  async function submitForm(form) {
    const kind=form.dataset.form,data=formData(form),id=form.dataset.id;
    if(kind==='date-filter'){const query=new URLSearchParams();if(get(data,'date'))query.set('date',get(data,'date'));return navigate(form.dataset.path+(query.size?'?'+query:''));}
    if(kind==='works-filter'){const query=new URLSearchParams();for(const key of ['event','placement'])if(get(data,key))query.set(key,get(data,key));return navigate('/works?'+query);}
    if(kind==='request-code')return sendCode(get(data,'phone'));
    if(kind==='verify'){
      if(!state.challenge||Date.now()>=state.challenge.expiresAt)throw new ApiError(400,t('expired'));
      state.user=await api.request('auth/verify-code/','POST',{challenge_id:state.challenge.id,code:get(data,'code')});
      state.challenge=null;const destination=state.afterLogin;state.afterLogin=null;
      await loadPublic();return navigate(destination||dashboard());
    }
    if(kind==='booking'){
      captureBooking(form);
      if(!state.user){state.afterLogin='/booking';return navigate('/account');}
      const o=await api.request('bookings/','POST',state.draft);
      state.draft={event:'wedding',package:'standard',extras:[],client_name:'',date:'',location:'',client_note:''};
      toast(t('sent'));return navigate('/account/order/'+o.id);
    }
    if(kind==='change-request'){
      const payload={kind:get(data,'kind'),reason:get(data,'reason')};
      if(payload.kind==='reschedule'){payload.requested_date=get(data,'requested_date');if(get(data,'requested_time'))payload.requested_time=get(data,'requested_time');}
      await api.request(`bookings/${id}/change-requests/`,'POST',payload);
    }else if(kind==='booking-edit'){
      const o=state.orders.get(id),payload=changedPayload(form,o);
      if(payload.status==='cancelled'&&!window.confirm(t('cancelConfirm')))return;
      await api.request(`bookings/${id}/`,'PATCH',payload);
    }else if(kind==='reprice'){
      await api.request(`bookings/${id}/`,'PATCH',{version:state.orders.get(id).version,package:get(data,'package'),extras:data.getAll('extras').map(String)});
    }else if(kind==='adjustment'){
      await api.request(`bookings/${id}/`,'PATCH',{version:state.orders.get(id).version,adjustment:get(data,'adjustment'),adjustment_reason:get(data,'adjustment_reason')});
    }else if(kind==='decision'){
      const payload={version:state.orders.get(id).version,approve:get(data,'approve')==='yes',note:get(data,'note')};
      if(payload.approve&&form.dataset.kind==='reschedule')payload.crew=readCrew(form);
      await api.request(`management/change-requests/${form.dataset.change}/decision/`,'POST',payload);
    }else if(kind==='prices'){
      const items=state.catalog.filter(item=>Number(get(data,item.code))!==Number(item.price)).map(item=>({code:item.code,price:get(data,item.code),revision:item.revision}));
      if(items.length)await api.request('management/prices/','PATCH',{items});
      state.catalog=await api.request('catalog/');
    }else if(kind==='binding'){
      await api.request('management/bindings/','PUT',{member:Number(form.dataset.member),phone:get(data,'phone')});
    }else if(kind==='profile'){
      const payload=new window.FormData();payload.set('bio_ru',get(data,'bio_ru'));payload.set('bio_tg',get(data,'bio_tg'));
      const photo=data.get('photo');if(photo?.size){if(photo.size>10*1024*1024)throw new ApiError(400,t('tooLarge'));payload.set('photo',photo);}
      await api.request('me/profile/','PATCH',payload);state.user=await api.request('me/');state.team=await api.request('team/');
    }else if(kind==='video'){
      const payload=new window.FormData();for(const key of ['title_ru','title_tg','event','placement'])payload.set(key,get(data,key));
      payload.set('permission_confirmed',data.has('permission_confirmed')?'true':'false');
      const video=data.get('video');if(video?.size){if(video.size>200*1024*1024)throw new ApiError(400,t('tooLarge'));payload.set('video',video);}
      await api.request(id?`portfolio/${id}/`:'portfolio/',id?'PATCH':'POST',payload);
      toast(t('saved'));return navigate(dashboard()+'/videos');
    }else if(kind==='content'){
      const type=form.dataset.kind,payload=serialForm(form);
      if(type==='reviews'){payload.consent=data.has('consent');payload.published=data.has('published');}
      else payload.order=Number(payload.order);
      await api.request(type+'/'+(id?id+'/':''),id?'PATCH':'POST',payload);
      await loadPublic();toast(t('saved'));return navigate('/management/content/'+type);
    }
    toast(t('saved'));if(form.isConnected)await render(true);
  }
  async function clickAction(button) {
    const action=button.dataset.action;
    if(action==='language'){captureBooking(content.querySelector('[data-form="booking"]'));state.language=button.dataset.language;try{window.localStorage.setItem('creative-language',state.language);}catch{}return render(true);}
    if(action==='logout'){await api.request('auth/logout/','POST',{});api.csrfToken=null;state.user=null;state.orders.clear();state.challenge=null;state.afterLogin=null;await loadPublic();return navigate('/account');}
    if(action==='refresh')return render(true);
    if(action==='reload-data'){await loadPublic();return render(true);}
    if(action==='change-phone'){state.challenge=null;return render(true);}
    if(action==='resend')return sendCode(state.challenge.phone);
    if(action==='team-next'||action==='team-prev'){document.getElementById('team-track')?.scrollBy({left:action==='team-next'?285:-285,behavior:'smooth'});return;}
    if(action==='retry-crew'){const form=button.closest('form'),o=state.orders.get(form.dataset.id);return loadCrew(form,o,form.dataset.date||form.elements.date?.value||o.date);}
    if(action==='unbind'){if(!window.confirm(t('unbindConfirm')))return;await api.request(`management/bindings/${button.dataset.member}/`,'DELETE');}
    else if(action==='delete-video'){if(!window.confirm(t('deleteConfirm')))return;await api.request(`portfolio/${button.dataset.id}/`,'DELETE');}
    else if(action==='delete-content'){if(!window.confirm(t('deleteConfirm')))return;await api.request(`${button.dataset.kind}/${button.dataset.id}/`,'DELETE');await loadPublic();}
    else return;
    toast(t('saved'));return render(true);
  }
  function onClick(event) {
    if(event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
    const anchor=event.target.closest?.('a[href^="#/"]');
    if(anchor){event.preventDefault();pending=navigate(anchor.getAttribute('href').slice(1));return;}
    const button=event.target.closest?.('[data-action]');if(!button||button.disabled)return;
    pending=clickAction(button).catch(error=>toast(errorText(error)));
  }
  function onSubmit(event) {
    const form=event.target.closest?.('form[data-form]');if(!form)return;
    event.preventDefault();if(state.mutating||!form.reportValidity())return;
    state.mutating=true;
    const buttons=[...form.querySelectorAll('button[type="submit"]')];buttons.forEach(b=>{b.disabled=true;b.dataset.label=b.textContent;b.textContent=t('saving');});
    const error=form.querySelector('[data-form-error]');if(error)error.textContent='';
    pending=submitForm(form).catch(problem=>{if(error&&form.isConnected)error.textContent=errorText(problem);else toast(errorText(problem));}).finally(()=>{
      state.mutating=false;buttons.forEach(b=>{b.disabled=false;b.textContent=b.dataset.label;});updateClocks();
    });
  }
  function onChange(event) {
    const input=event.target,form=input.closest?.('form');if(!form)return;
    if(form.dataset.form==='booking'){
      captureBooking(form);
      if(input.name==='event'){
        state.draft.package=packageValues(state.draft.event)[0];state.draft.extras=[];
        form.querySelector('#booking-package').innerHTML=select(t('package'),'package',packageValues(state.draft.event),state.draft.package);
      }
      if(input.name==='event'||input.name==='package'){
        if(input.name==='package')state.draft.package=input.value;
        if(state.draft.package==='premium')state.draft.extras=state.draft.extras.filter(c=>!['album','foteha_one','foteha_two'].includes(c));
        form.querySelector('#booking-extras').innerHTML=state.draft.event==='wedding'?extraChoices(state.draft.package,state.draft.extras):'';
      }
      if(input.name==='extras'&&input.checked&&['foteha_one','foteha_two'].includes(input.value)){
        form.querySelectorAll('input[name="extras"]').forEach(other=>{if(other!==input&&['foteha_one','foteha_two'].includes(other.value))other.checked=false;});
      }
      captureBooking(form);updateEstimate();
    }
    if(form.dataset.form==='change-request'&&input.name==='kind')updateChangeFields(form);
    if(form.dataset.form==='booking-edit'&&input.name==='date')pending=loadCrew(form,state.orders.get(form.dataset.id),input.value);
    if(input.name==='crew'){
      form.elements['duty-'+input.value].disabled=!input.checked;
      if(!input.checked&&input.dataset.conflict==='true')input.disabled=true;
    }
    if(form.dataset.form==='reprice'&&input.name==='package')form.querySelector('[data-quote-extras]').innerHTML=state.orders.get(form.dataset.id).event==='wedding'?extraChoices(input.value,[]):'';
    if(form.dataset.form==='reprice'&&input.name==='extras'&&input.checked&&['foteha_one','foteha_two'].includes(input.value))form.querySelectorAll('input[name="extras"]').forEach(other=>{if(other!==input&&['foteha_one','foteha_two'].includes(other.value))other.checked=false;});
  }
  const onInput=event=>{const form=event.target.closest?.('[data-form="booking"]');if(form)captureBooking(form);};
  const onHistory=()=>{pending=render();};
  async function start() {
    document.addEventListener('click',onClick);document.addEventListener('submit',onSubmit);
    content.addEventListener('change',onChange);content.addEventListener('input',onInput);
    window.addEventListener('popstate',onHistory);window.addEventListener('hashchange',onHistory);
    try{state.user=await api.request('me/');}catch(error){if(error.status!==403)state.user=null;}
    await loadPublic();await render(true);interval=window.setInterval(updateClocks,1000);
  }
  function destroy(){document.removeEventListener('click',onClick);document.removeEventListener('submit',onSubmit);content.removeEventListener('change',onChange);content.removeEventListener('input',onInput);window.removeEventListener('popstate',onHistory);window.removeEventListener('hashchange',onHistory);window.clearInterval(interval);window.clearTimeout(toastTimer);state.epoch++;}
  return {start,destroy,navigate,refresh:()=>render(true),idle:async()=>{await pending;await activeRender;}};
}

if(typeof window!=='undefined'&&document.getElementById('content')){
  const application=createApplication({document,window});
  application.start().catch(()=>{document.getElementById('content').textContent=translate('failed',document.documentElement.lang);});
}
