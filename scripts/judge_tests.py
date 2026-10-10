"""Hidden test definitions for the local learning judge."""
TESTS = {
"relu": r'''x=torch.tensor([-3.,-.1,2.5],requires_grad=True); y=relu(x)
check(torch.equal(y,torch.tensor([0.,0.,2.5])),"正负输入结果不正确")
y.sum().backward(); check(torch.equal(x.grad,torch.tensor([0.,0.,1.])),"梯度不正确")''',
"sigmoid": r'''x=torch.tensor([-100.,-1.,0.,1.,100.],dtype=torch.float64); y=sigmoid(x)
check_close(y,torch.sigmoid(x)); check(torch.isfinite(y).all(),"极值出现 NaN/Inf")''',
"softmax": r'''x=torch.tensor([[1000.,1001.,1002.],[-3.,0.,4.]],dtype=torch.float64)
check_close(my_softmax(x,1),torch.softmax(x,1)); check_close(my_softmax(x,0),torch.softmax(x,0))
check(torch.isfinite(my_softmax(x,1)).all(),"大数输入不稳定")''',
"gelu": r'''x=torch.linspace(-4,4,33,dtype=torch.float64); check_close(my_gelu(x),torch.nn.functional.gelu(x),atol=1e-6,rtol=1e-5)''',
"cosine-similarity": r'''a=torch.tensor([[1.,0.],[1.,1.],[0.,0.]]); b=torch.tensor([[0.,1.],[1.,-1.],[2.,3.]])
check_close(cosine_sim(a,b),torch.nn.functional.cosine_similarity(a,b,dim=-1,eps=1e-8))''',
"linear-warmup": r'''check(abs(linear_warmup(0,10,0.01)-0)<1e-12,"step=0 错误")
check(abs(linear_warmup(5,10,0.01)-0.005)<1e-12,"预热中点错误")
check(abs(linear_warmup(10,10,0.01)-0.01)<1e-12,"预热终点错误")
check(abs(linear_warmup(30,10,0.01)-0.01)<1e-12,"预热后应保持 base_lr")''',
"cosine-lr": r'''for args,expected in [((0,100,10,1.,0.1),0.),((5,100,10,1.,0.1),.5),((10,100,10,1.,0.1),1.),((100,100,10,1.,0.1),.1)]:
 check(abs(cosine_lr_schedule(*args)-expected)<1e-7,f"边界样例错误: {args}")
check(abs(cosine_lr_schedule(55,100,10,1.,0.1)-.55)<1e-7,"余弦中点错误")''',
"cross-entropy": r'''logits=torch.tensor([[1.,2.,3.],[-1.,0.,2.]],dtype=torch.float64,requires_grad=True); targets=torch.tensor([2,0])
got=cross_entropy_loss(logits,targets); ref=torch.nn.functional.cross_entropy(logits,targets)
check_close(got,ref); got.backward(); check(logits.grad is not None,"损失必须支持反向传播")''',
"kl-divergence": r'''p=torch.tensor([[1.,2.,-1.],[0.,0.,0.]],dtype=torch.float64); q=torch.tensor([[0.,1.,2.],[1.,-1.,0.]],dtype=torch.float64)
ref=(torch.softmax(p,-1)*(torch.log_softmax(p,-1)-torch.log_softmax(q,-1))).sum(-1).mean()
check_close(kl_divergence(p,q),ref)''',
"dpo-loss": r'''pc=torch.tensor([-1.,-2.]); pr=torch.tensor([-2.,-1.]); rc=torch.tensor([-1.4,-1.]); rr=torch.tensor([-1.8,-1.5]); beta=.2
ref=-torch.nn.functional.logsigmoid(beta*((pc-pr)-(rc-rr))).mean(); check_close(dpo_loss(pc,pr,rc,rr,beta),ref)''',
"ppo-loss": r'''n=torch.log(torch.tensor([1.1,.7,1.5])); o=torch.zeros(3); a=torch.tensor([1.,-1.,2.]); clip=.2
ratio=torch.exp(n-o); ref=-torch.min(ratio*a,torch.clamp(ratio,1-clip,1+clip)*a).mean()
check_close(ppo_loss(n,o,a,clip),ref)''',
"flow-matching": r'''out=torch.tensor([[1.,2.],[3.,4.]],requires_grad=True); x0=torch.tensor([[0.,1.],[2.,1.]]); x1=torch.tensor([[2.,3.],[2.,5.]])
ref=torch.nn.functional.mse_loss(out,x1-x0); got=flow_matching_loss(out,x0,x1,torch.tensor([.2,.8])); check_close(got,ref); got.backward()''',
"label-smoothing": r'''logits=torch.tensor([[2.,0.,-1.],[0.,1.,3.]],dtype=torch.float64); target=torch.tensor([0,2]); s=.1
check_close(label_smoothing(logits,target,s),torch.nn.functional.cross_entropy(logits,target,label_smoothing=s))''',
"temperature-scaling": r'''x=torch.tensor([[1.,2.,4.],[-1.,0.,1.]],dtype=torch.float64)
check_close(temperature_scale(x,2.),x/2.); check_close(temperature_scale(x,.5),x/.5)''',
}
JUDGEABLE = frozenset(TESTS)
