const CSRF=document.querySelector('meta[name=csrf]').content,$=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(p,b){const r=await fetch(p,b?{method:'POST',headers:{'X-CSRF-Token':CSRF,'Content-Type':'application/json'},body:JSON.stringify(b)}:{});if(r.status===401){location='/admin/login';return}const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||r.status);return j}
async function load(){const o=await api('/admin/api/overview'),c=o.cfg;
$('#main').innerHTML=`<div class="card"><h3>Master prompt (সব ইউজারের জন্য)</h3><textarea id="mp" style="min-height:260px">${esc(c.masterPrompt)}</textarea>
<label>ডিফল্ট দৈনিক রিপ্লাই লিমিট (প্রতি ইউজার)</label><input id="dl" type="number" value="${c.defaultDailyLimit}"><label>ডেটা রিটেনশন (দিন)</label><input id="rd" type="number" value="${c.retentionDays}"><label>লিংক ক্যাশ (মিনিট)</label><input id="lt" type="number" value="${c.linkTtlMinutes}">
<button id="sv">সেভ</button> <span id="out" class="mut"></span></div>
<div class="card"><h3>ইউজার (${o.users.length})</h3><table><tr><th>নাম</th><th>মোড</th><th>আজ: মেসেজ/AI/লিমিট-হিট</th><th>লিমিট</th><th></th></tr>${o.users.map(u=>`<tr><td>${esc(u.name)}<br><span class="mut">${esc(u.username)}</span></td><td>${u.mode}</td><td>${u.today.messages_in}/${u.today.ai_replies}/${u.today.limit_hits}</td><td><input style="width:70px" data-l="${esc(u.id)}" value="${u.dailyLimit||''}" placeholder="ডিফল্ট"></td><td><button class="sm ${u.disabled?'':'rd'}" data-d="${esc(u.id)}" data-v="${u.disabled?0:1}">${u.disabled?'চালু করুন':'বন্ধ করুন'}</button></td></tr>`).join('')}</table></div>
<div class="card"><h3>পেজ (${o.pages.length})</h3><table>${o.pages.map(p=>`<tr><td>${esc(p.name)}</td><td class="mut">${esc(p.owner)}</td><td>${p.connected?'✅':'❌'} ${p.auto?'🤖':''} ${p.comments?'💬':''}</td></tr>`).join('')}</table></div>
<div class="card"><h3>সাম্প্রতিক এরর</h3><table>${o.errors.map(e=>`<tr><td>${new Date(e.ts*1000).toLocaleString()}</td><td>${esc(e.where)}</td><td>${esc(e.msg)}</td></tr>`).join('')||'<tr><td class="mut">কোনো এরর নেই</td></tr>'}</table></div>`;
$('#sv').onclick=async()=>{try{await api('/admin/api/config',{masterPrompt:$('#mp').value,defaultDailyLimit:+$('#dl').value,retentionDays:+$('#rd').value,linkTtlMinutes:+$('#lt').value});$('#out').textContent='সেভ হয়েছে ✅'}catch(e){alert(e.message)}};
document.querySelectorAll('[data-d]').forEach(b=>b.onclick=async()=>{await api('/admin/api/user/'+b.dataset.d,{disabled:b.dataset.v==='1'});load()});
document.querySelectorAll('[data-l]').forEach(i=>i.onchange=async()=>{await api('/admin/api/user/'+i.dataset.l,{dailyLimit:+i.value||0});load()})}
load().catch(e=>alert(e.message));
