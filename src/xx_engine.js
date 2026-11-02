'use strict';
// The host owns risk, account authority, transport and reconciliation.
// Declarative plugins only resolve strategy profiles; old campaigns retain frozen policies.
class XXEngine extends XIIIEngine {
 pluginFor(book){const m=HXX.validate(this.cfg.xx_books?.[book]||HXX.host(book));if(m.book!==book)throw Error('Plugin asignado al libro incorrecto');return m;}
 profileFor(row,p=this.profile()){return HXX.securities(this.pluginFor(row.book||'equity'),p);}
 decision(row,p,selected){const m=this.pluginFor(row.book||'equity'),profile=this.profileFor(row,p),r=super.decision(row,profile,selected);r.plugin_id=m.id;r.plugin_version=m.version;r.resolved_profile=profile;if(r.ask&&m.binding==='fixed'&&this.cfg.mode==='live'){r.reasons=[...(r.reasons||[]),'PLUGIN EXPERIMENTAL: SÓLO PAPER / LABORATORIO'];r.state=r.reasons[0];r.reason=r.reasons.join(' · ');}return r;}
 campaignPlugin(row,p){return HXX.stamp(this.pluginFor(row.book),p);}
 evidenceFingerprint(){return HLab.stable({base:super.evidenceFingerprint(),plugins:this.cfg.xx_books||null});}
 hasFixedPlugin(){return ['equity','etf'].some(book=>this.pluginFor(book).binding==='fixed');}
 labOwnsPromotion(){return this.hasFixedPlugin()||super.labOwnsPromotion?.();}
 async research(){if(this.hasFixedPlugin())throw Error('Plugin fijo: recopila PAPER; usa el enlace canónico para el loop de promoción.');return super.research();}
}
