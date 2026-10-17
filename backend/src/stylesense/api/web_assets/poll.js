(function(){
  var P=window.POLL, key='ss_voter', token;
  try{token=localStorage.getItem(key);}catch(e){}
  if(!token){var a=new Uint8Array(18);crypto.getRandomValues(a);token=Array.from(a,function(b){return('0'+b.toString(16)).slice(-2)}).join('');try{localStorage.setItem(key,token);}catch(e){}}
  var H={'X-Voter-Token':token,'Content-Type':'application/json'};
  var status=document.getElementById('status');
  function show(d,mine){
    if(d.total_votes==null){return;}
    var max=Math.max.apply(null,d.options.map(function(o){return o.votes||0}).concat([1]));
    var lead=d.options.reduce(function(a,b){return (b.votes||0)>(a.votes||0)?b:a});
    d.options.forEach(function(o){
      var el=document.querySelector('.option[data-id="'+o.option_id+'"]'); if(!el)return;
      el.classList.add('voted'); el.classList.toggle('lead', d.total_votes>0 && o.option_id===lead.option_id);
      if(mine&&o.option_id===mine) el.classList.add('mine');
      el.querySelector('.fill').style.width=Math.max(4,(o.votes||0)/max*100)+'%';
      el.querySelector('.count').textContent=(o.votes||0)+(o.votes===1?' vote':' votes');
    });
    status.textContent=d.total_votes+(d.total_votes===1?' vote so far':' votes so far')+(d.status==='open'?'. Thanks for voting!':'. Voting has closed.');
  }
  var mine=null; try{mine=localStorage.getItem('ss_vote_'+P.slug);}catch(e){}
  fetch('/v1/public/polls/'+P.slug,{headers:H}).then(function(r){return r.json()}).then(function(d){show(d,mine)});
  document.querySelectorAll('.option').forEach(function(btn){
    btn.addEventListener('click',function(){
      if(!P.open)return;
      var id=btn.getAttribute('data-id');
      fetch('/v1/public/polls/'+P.slug+'/votes',{method:'POST',headers:H,body:JSON.stringify({option_id:id})})
        .then(function(r){return r.json().then(function(d){return{ok:r.ok,d:d}})})
        .then(function(x){
          if(x.ok){try{localStorage.setItem('ss_vote_'+P.slug,id);}catch(e){} if(navigator.vibrate)navigator.vibrate(12); show(x.d,id);}
          else{status.textContent=x.d.detail||x.d.title||'Could not vote.';}
        });
    });
  });
})();
