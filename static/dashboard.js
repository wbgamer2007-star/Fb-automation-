const CSRF=document.querySelector('meta[name=csrf]').content,$=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(p,m='GET',b=null,form=null){const o={method:m,headers:{'X-CSRF-Token':CSRF}};if(form)o.body=form;else if(b){o.headers['Content-Type']='application/json';o.body=JSON.stringify(b)}
 const r=await fetch(p,o);if(r.status===401){location='/login';return}const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||('ত্রুটি '+r.status));return j}
const ago=t=>{if(!t)return'';const s=Date.now()/1000-t;return s<60?'এইমাত্র':s<3600?Math.floor(s/60)+' মিনিট আগে':s<86400?Math.floor(s/3600)+' ঘণ্টা আগে':Math.floor(s/86400)+' দিন আগে'};
let S={},tab='inbox',pid=null;
const TABS={inbox:'ইনবক্স',comments:'কমেন্ট',stats:'অ্যানালিটিক্স',settings:'নির্দেশনা ও সেটিংস',ai:'AI কী',cmd:'কমান্ড',reports:'রিপোর্ট',acct:'অ্যাকাউন্ট'};
const alertErr=e=>alert(e.message||e);
async function boot(){S=await api('/api/bootstrap');$('#who').textContent=S.user.name||'';pid=pid||(S.pages[0]||{}).id;
 $('#tabs').innerHTML=Object.entries(TABS).map(([k,v])=>`<button data-t="${k}" class="${k===tab?'on':''}">${v}</button>`).join('');
 $('#tabs').onclick=e=>{const t=e.target.dataset.t;if(t){tab=t;boot()}};
 if(!S.pages.length&&tab!=='acct'){$('#main').innerHTML='<div class="card">কোনো পেজ কানেক্ট নেই। <a class="btn" href="/connect">পেজ কানেক্ট করুন</a></div>';return}
 ({inbox,comments,stats,settings,ai,cmd,reports,acct})[tab]()}
const pageSel=()=>S.pages.length>1?`<select id="ps">${S.pages.map(p=>`<option value="${esc(p.id)}" ${p.id===pid?'selected':''}>${esc(p.name)}</option>`).join('')}</select>`:'';
const bindPs=()=>{const s=$('#ps');if(s)s.onchange=()=>{pid=s.value;boot()}};
const curPage=()=>S.pages.find(p=>p.id===pid)||S.pages[0];
async function inbox(){const l=await api('/api/conversations');
 $('#main').innerHTML='<div class="card">'+(l.map(c=>`<div class="item" data-c="${esc(c.id)}"><b>${esc(c.name)}</b> <span class="tag">${c.manual?'👤 হাতে':'🤖 AI'}</span> <span class="mut">${esc(c.page)} · ${ago(c.updatedAt)}</span><div class="mut">${esc(c.last)}</div></div>`).join('')||'<p class="mut">এখনো কোনো মেসেজ নেই</p>')+'</div>';
 $('#main').onclick=e=>{const d=e.target.closest('[data-c]');if(d)chat(d.dataset.c)}}
async function chat(id){const c=await api('/api/conversation/'+id);
 $('#main').innerHTML=`<div class="card"><button class="sm gr" id="bk">← ফিরুন</button> <b>${esc(c.name)}</b> <button class="sm ${c.manual?'':'gr'}" id="tk">${c.manual?'AI চালু করুন':'নিজে হাতে নিন (AI বন্ধ)'}</button>
 <div>${c.msgs.map(m=>`<div class="msg ${m.r}">${esc(m.t)}<div class="mut">${m.r==='user'?'কাস্টমার':m.r==='human'?'আপনি':'AI'} · ${ago(m.ts)}</div></div>`).join('')}</div>
 <textarea id="rt" style="min-height:60px" placeholder="উত্তর লিখুন…"></textarea><button id="sd">পাঠান</button></div>`;
 $('#main').onclick=null;$('#bk').onclick=inbox;
 $('#tk').onclick=async()=>{try{await api(`/api/conversation/${id}/takeover`,'POST',{on:!c.manual});chat(id)}catch(e){alertErr(e)}};
 $('#sd').onclick=async()=>{try{await api(`/api/conversation/${id}/reply`,'POST',{text:$('#rt').value});chat(id)}catch(e){alertErr(e)}}}
async function comments(){const l=await api('/api/comments');
 $('#main').innerHTML='<div class="card">'+(l.map(c=>`<div class="row" style="display:block"><b>${esc(c.from||'')}</b> <span class="tag">${esc(c.type)}${c.action?' · '+esc(c.action):''}</span> <span class="mut">${ago(c.ts)}</span><div>${esc(c.message)}</div>${c.reply?`<div class="msg model">${esc(c.reply)}</div>`:''}</div>`).join('')||'<p class="mut">কমেন্ট লগ খালি (সেটিংস থেকে কমেন্ট চালু করুন)</p>')+'</div>'}
async function stats(){const a=await api('/api/analytics');
 $('#main').innerHTML=`<div class="card"><p>আজকের AI রিপ্লাই: <b>${S.used}</b> / ${S.limit} (ডিফল্ট কী ব্যবহার করলে)</p><table><tr><th>তারিখ</th><th>মেসেজ</th><th>AI রিপ্লাই</th><th>কমেন্ট</th><th>কমেন্ট রিপ্লাই</th></tr>${a.days.map(d=>`<tr><td>${d.date}</td><td>${d.messages_in}</td><td>${d.ai_replies}</td><td>${d.comments}</td><td>${d.comment_replies}</td></tr>`).join('')}</table></div>
 <div class="card"><b>কাস্টমাররা কী নিয়ে জিজ্ঞেস করে</b><ul>${a.topics.map(t=>`<li>${esc(t)}</li>`).join('')||'<li class="mut">রিপোর্ট চালু করলে এখানে দেখা যাবে</li>'}</ul></div>`}
function settings(){const p=curPage();
 $('#main').innerHTML=`<div class="card">${pageSel()}<h3>${esc(p.name)}</h3>
 <label class="row"><input type="checkbox" id="ar" ${p.autoReplyEnabled?'checked':''}> মেসেঞ্জারে অটো-রিপ্লাই</label>
 <label class="row"><input type="checkbox" id="ce" ${p.commentsEnabled?'checked':''}> কমেন্টে AI রিপ্লাই</label>
 <label class="row"><input type="checkbox" id="dr" ${p.dailyReportEnabled?'checked':''}> দৈনিক রিপোর্ট</label>
 <label>গালি/অপমানজনক কমেন্টে:</label><select id="aa"><option value="hide">লুকিয়ে রাখুন</option><option value="delete">মুছে ফেলুন</option><option value="none">কিছু করবেন না</option></select>
 <h4>কাস্টম নির্দেশনা (AI কী করবে, কীভাবে বলবে)</h4><textarea id="ins" placeholder="যেমন: আপনি ABC শপের সহকারী। পণ্যের তালিকা ও দাম: https://docs.google.com/…">${esc(p.instructions)}</textarea>
 <h4>লিংক সোর্স (প্রতি লাইনে একটি; Google Sheet/Doc বা পাবলিক ওয়েবপেজ)</h4><textarea id="ls" style="min-height:80px">${esc((p.linkSources||[]).join('\n'))}</textarea>
 <button id="sv">সেভ করুন</button> <button class="gr" id="rf">লিংক রিফ্রেশ</button><div id="out" class="mut"></div>
 <p><button class="rd sm" id="dc">এই পেজ ডিসকানেক্ট করুন</button> <a href="/connect">আরও পেজ যোগ করুন</a></p></div>`;bindPs();$('#aa').value=p.abuseAction||'hide';
 const collect=()=>({autoReplyEnabled:$('#ar').checked,commentsEnabled:$('#ce').checked,dailyReportEnabled:$('#dr').checked,abuseAction:$('#aa').value,instructions:$('#ins').value,linkSources:$('#ls').value.split('\n').map(x=>x.trim()).filter(Boolean)});
 $('#sv').onclick=async()=>{try{await api(`/api/page/${pid}/settings`,'POST',collect());$('#out').textContent='সেভ হয়েছে ✅';S=await api('/api/bootstrap')}catch(e){alertErr(e)}};
 $('#rf').onclick=async()=>{try{await api(`/api/page/${pid}/settings`,'POST',collect());const r=await api(`/api/page/${pid}/links/refresh`,'POST',{});$('#out').innerHTML=r.results.map(x=>`${esc(x.url)} → ${x.error?'❌ '+esc(x.error):'✅ '+x.chars+' অক্ষর'}`).join('<br>')||'কোনো লিংক নেই'}catch(e){alertErr(e)}};
 $('#dc').onclick=async()=>{if(confirm('ডিসকানেক্ট করবেন?')){try{await api(`/api/page/${pid}/disconnect`,'POST',{});pid=null;boot()}catch(e){alertErr(e)}}}}
function ai(){const a=S.ai,P=['gemini','groq','mistral','cerebras','openrouter'];
 $('#main').innerHTML=`<div class="card"><h3>AI কী</h3><label class="row"><input type="radio" name="m" value="default" ${a.mode==='default'?'checked':''}> মালিকের ডিফল্ট কী (দিনে সর্বোচ্চ ${S.limit}টি রিপ্লাই)${a.defaultAvailable?'':' — এখনো সেট নেই'}</label>
 <label class="row"><input type="radio" name="m" value="own" ${a.mode==='own'?'checked':''}> আমার নিজের কী (সীমাহীন; এনক্রিপ্টেড থাকে)</label>
 ${P.map(k=>`<label>${k} key ${a.has[k]?'✅ সেভ আছে (নতুন দিলে বদলাবে; মুছতে __clear__ লিখুন)':''}</label><input id="k_${k}" type="password" autocomplete="off" placeholder="API key"><input id="m_${k}" placeholder="মডেল (ঐচ্ছিক, কমা দিয়ে)" value="${esc(a.models[k]||'')}">`).join('')}
 <label>Custom OpenAI-compatible ${a.has.customKey?'✅':''}</label><input id="cu" placeholder="Base URL, যেমন https://api.example.com/v1" value="${esc(a.customBaseUrl)}"><input id="k_custom" type="password" placeholder="API key"><input id="m_custom" placeholder="মডেল নাম (বাধ্যতামূলক)" value="${esc(a.models.custom||'')}">
 <button id="sv">সেভ</button> <span id="out" class="mut"></span><p class="mut">ভয়েস মেসেজের জন্য Gemini কী লাগবে।</p></div>`;
 $('#sv').onclick=async()=>{const keys={},models={};[...P,'custom'].forEach(k=>{keys[k]=$('#k_'+k).value;models[k]=$('#m_'+k).value});
  try{await api('/api/ai','POST',{mode:document.querySelector('input[name=m]:checked').value,keys,models,customBaseUrl:$('#cu').value});$('#out').textContent='সেভ হয়েছে ✅';boot()}catch(e){alertErr(e)}}}
function cmd(){$('#main').innerHTML=`<div class="card">${pageSel()}<h3>বট কমান্ড</h3><p class="mut">যেমন: “এটা পেজে পোস্ট করো: ঈদ অফার চলছে…” — চাইলে ছবি জুড়ুন।</p>
 <textarea id="ct" placeholder="কমান্ড লিখুন"></textarea><input type="file" id="im" accept="image/*"><button id="go">পাঠান</button><div id="out"></div></div>`;bindPs();
 $('#go').onclick=async()=>{if(!confirm('পেজে পোস্ট হবে। নিশ্চিত?'))return;const f=new FormData();f.append('pageId',pid);f.append('text',$('#ct').value);if($('#im').files[0])f.append('image',$('#im').files[0]);
  $('#out').textContent='পাঠানো হচ্ছে…';try{const r=await api('/api/command','POST',null,f);$('#out').textContent=r.message}catch(e){$('#out').textContent=e.message}}}
async function reports(){const l=await api('/api/reports');const li=a=>(a||[]).map(x=>`<li>${esc(x)}</li>`).join('');
 $('#main').innerHTML=l.map(r=>`<div class="card"><b>${esc(r.date)}</b> · ${esc(r.pageName)} · <span class="tag">${esc(r.sentiment)}</span><p>${esc(r.summary)}</p><b>👍 পছন্দ</b><ul>${li(r.liked)}</ul><b>👎 অপছন্দ</b><ul>${li(r.disliked)}</ul><b>❓ জিজ্ঞাসা</b><ul>${li(r.asked)}</ul><b>💡 পরামর্শ</b><ul>${li(r.suggestions)}</ul></div>`).join('')||'<div class="card mut">কোনো রিপোর্ট নেই। সেটিংসে “দৈনিক রিপোর্ট” চালু করুন।</div>'}
function acct(){$('#main').innerHTML=`<div class="card"><p>ইউজারনেম: <b class="mono">${esc(S.user.username)}</b></p><button id="pw">নতুন পাসওয়ার্ড বানান</button><div id="out" class="mono"></div><p><a href="/connect">পেজ কানেক্ট/যোগ করুন</a> · <a href="/privacy">Privacy</a></p></div>`;
 $('#pw').onclick=async()=>{if(confirm('পুরনো পাসওয়ার্ড বাতিল হবে')){const r=await api('/api/password','POST',{});$('#out').textContent='নতুন পাসওয়ার্ড: '+r.password+' (লিখে রাখুন)'}}}
boot().catch(alertErr);
