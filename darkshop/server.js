const express = require("express");
const app = express();
const port = process.env.PORT || 9000;

const shell = (title, body, mode) => `<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title}</title>
<style>
body{margin:0;background:#f5f7fb;font-family:Arial,sans-serif;color:#17263b}
header{background:#08203b;color:#fff;padding:18px 7%;font-weight:800}
main{max-width:920px;margin:38px auto;padding:0 18px}
.card{background:#fff;border:1px solid #dfe7f0;border-radius:18px;padding:28px;box-shadow:0 10px 35px rgba(15,35,60,.08)}
button{border:0;border-radius:10px;padding:13px 20px;background:#1769e0;color:#fff;font-weight:700;font-size:15px;cursor:pointer}
button.secondary{background:#eef3f8;color:#20364f}
.price{font-size:38px;font-weight:800;margin:15px 0}
.row{padding:14px 0;border-bottom:1px solid #e5ebf2}
.total{font-size:32px;font-weight:800}
.timer{margin:18px 0;padding:14px;border-radius:10px;background:#fff1e7;color:#9a4300;font-weight:700}
.fee{color:#9a4300;font-weight:700}
.badge{display:inline-block;padding:5px 9px;border-radius:20px;background:#eef5ff;color:#1769e0;font-size:12px;font-weight:700}
.muted{color:#6e7d90}
</style></head>
<body><header>Demo Commerce Store <span style="float:right;font-size:12px;font-weight:400">Sentinel Benchmark · ${mode==="dark"?"Manipulative":"Clean Control"}</span></header>
<main><div class="card">${body}</div></main></body></html>`;

function home(mode){
 return shell("Search", `<span class=badge>Search</span><h1>Travel Headphones</h1>
 <p class=muted>Noise cancelling · Wireless · 2-year warranty</p>
 <div class=price>₹499</div>
 <button onclick="location='/product?mode=${mode}'">Select Product</button>`, mode);
}

function product(mode){
 const timer = mode==="dark"
 ? `<div class=timer data-testid=urgency-timer>Only <span id=secs>120</span>s left — offer ends soon!</div>
<script>
const end=Date.now()+120000;
const tick=()=>{const el=document.getElementById("secs");if(!el)return;
const left=Math.max(0,Math.ceil((end-Date.now())/1000));el.textContent=left;
if(left>0)setTimeout(tick,250)};tick();
</script>`
 : `<div class=timer data-testid=urgency-timer>Offer available while stock lasts</div>`;
 return shell("Product", `<span class=badge>Product</span><h1>Wireless Travel Headphones</h1>
 <p class=muted>Noise cancelling · Wireless · 2-year warranty</p>
 <div class=price>₹499</div>${timer}
 <button onclick="location='/cart?mode=${mode}'">Add to Cart</button>`, mode);
}

function cart(mode){
 return shell("Cart", `<span class=badge>Cart</span><h1>Your Cart</h1>
 <div class=row data-testid=cart-item>Wireless Travel Headphones — ₹499</div>
 <label style="display:block;padding:16px 0">
 <input id=protection type=checkbox> Add Travel Protection — ₹49
 </label>
 ${mode==="dark"?`<div class=row data-testid=cart-item>Travel Protection — ₹49 <span style="color:#b42318">(added by site)</span></div>`:""}
 <p class=muted>${mode==="dark"?"The optional protection item is present even though the checkbox was not selected.":"Optional protection remains opt-in."}</p>
 <button onclick="location='/review?mode=${mode}'">Review Order</button>`, mode);
}

function review(mode){
 return shell("Review", `<span class=badge>Review</span><h1>Review Order</h1>
 <div class=row>Wireless Travel Headphones</div>
 <div class=total data-testid=visible-total>₹499</div>
 <p class=muted>Delivery: Free</p>
 <button onclick="location='/checkout?mode=${mode}'">Checkout</button>`, mode);
}

function checkout(mode){
 const dark = mode==="dark";
 const gate = dark
   ? `<div class=row style="margin-top:18px"><label><input id=marketing-consent type=checkbox> I agree to receive promotional messages</label>
      <p class=muted data-testid=forced-action-note>Required to continue with payment.</p></div>
      <button id=pay-now disabled style="opacity:.45;cursor:not-allowed">Pay Now</button>`
   : `<button id=pay-now>Pay Now</button>`;
 return shell("Checkout", `<span class=badge>Checkout</span><h1>Complete your order</h1>
 <div class=row>Wireless Travel Headphones</div>
 ${dark?`<p class=fee data-testid=mandatory-fee>Mandatory Processing Fee: ₹129</p>
 <div class=total data-testid=visible-total>₹628</div>
 <p data-testid=decline-copy style="margin:22px 0;font-weight:700">No, I don't want to save money and protect my journey</p>`
 :`<p>Taxes and fees: ₹0</p><div class=total data-testid=visible-total>₹499</div>
 <p data-testid=decline-copy>No thanks</p>`}
 ${gate}
 <script>
 const c=document.getElementById('marketing-consent');
 if(c)c.addEventListener('change',()=>{const b=document.getElementById('pay-now');b.disabled=!c.checked;b.style.opacity=c.checked?'1':'.45';b.style.cursor=c.checked?'pointer':'not-allowed'});
 </script>`, mode);
}

app.get("/",(req,res)=>res.send(home(req.query.mode==="clean"?"clean":"dark")));
app.get("/product",(req,res)=>res.send(product(req.query.mode==="clean"?"clean":"dark")));
app.get("/cart",(req,res)=>res.send(cart(req.query.mode==="clean"?"clean":"dark")));
app.get("/review",(req,res)=>res.send(review(req.query.mode==="clean"?"clean":"dark")));
app.get("/checkout",(req,res)=>res.send(checkout(req.query.mode==="clean"?"clean":"dark")));

app.listen(port,()=>console.log(`Demo Commerce Store on http://127.0.0.1:${port}`));
