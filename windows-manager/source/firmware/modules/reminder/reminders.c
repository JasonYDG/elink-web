/* Eight offline BWR reminders with device-run daily/weekly recurrence. All flash operations stay in 26000..35fff.
   Slot state is programmed last; application banks and panel settings are untouched. */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef signed int i32;
#define S ((volatile u8 *)0x07fd1980)
#define E ((volatile u32 *)0x07fd04dc)
#define G ((volatile u32 *)0x07fcdd98)
#define BW ((u8 *)0x07fcdedc)
#define RR ((u8 *)0x07fcf15c)
#define CALL0(a) ((void (*)(void))((a)|1))()
#define READ(a,n,p) ((unsigned (*)(u32,unsigned,void *))0x07fc6829)(a,n,p)
#define WRITE(a,p,n) ((void (*)(u32,const void *,unsigned))0x07fc67c5)(a,p,n)
#define ERASE(a,n) ((void (*)(u32,unsigned))0x07fc671d)(a,n)
#define EXTRA __attribute__((section(".reminder.extra"),noinline))
#define MAIN __attribute__((section(".reminder.main"),noinline))
#define MAGIC 0x314d5245u
#define READY 0xfe
#define FIRED 0xfc
#define CANCELLED 0xf8
struct Entry {u32 token,due,next,last; i32 zone; u8 state,mask,check,duration;};
struct Rem {struct Entry entries[8];u32 token,due,expected,product_crc,expiry,hash; i32 offset;u16 received;u8 loaded,writing,slot,trigger,offset_valid,age,last_slot,alert,meta_received;};
#define R ((volatile struct Rem *)0x07fc8500)
typedef char retained_reminder_state_fits[sizeof(struct Rem)<=256?1:-1];
extern void product_battery(int,int,int);
extern void product_ink(u32,int,int,const char *,int);
int product_reminder_tick(void);
extern int product_album_restore(void);
__attribute__((section(".clock.extra"))) int product_reminder_blocked(void){return R->loaded&&(R->writing||R->alert!=255);}
EXTRA static u32 utc(void);
EXTRA static void summary(u32);
EXTRA static u32 occurrence(volatile struct Entry *,u32);
#define DIV ((u32 (*)(u32,u32))0x07f1dfb9)
#define TEXT ((void (*)(int,int,const char *))0x07fc3b4d)
#define FORMAT ((int (*)(char *,const char *,...))0x07fc7051)
static u32 addr(unsigned slot){return 0x26000+(slot<<13);}
static u32 get32(const u8 *p){return p[0]|(p[1]<<8)|(p[2]<<16)|((u32)p[3]<<24);}
static void put32(u8 *p,u32 v){for(unsigned i=0;i<4;i++){p[i]=v;v>>=8;}}
EXTRA u32 product_crc(u32 c,const u8 *p,unsigned n){while(n--){c^=*p++;for(unsigned i=0;i<8;i++)c=(c>>1)^((0-(c&1))&0xedb88320u);}return c;}
EXTRA void product_flash_write(u32 a,const u8 *p,unsigned n){
    while(n){unsigned count=256-(a&255);if(count>n)count=n;WRITE(a,p,count);CALL0(0x07fc6990);a+=count;p+=count;n-=count;}
}
EXTRA void product_publish(const u8 *p,unsigned n){
    unsigned task=((unsigned (*)(unsigned))0x07f0283f)(0xfd);
    u8 *m=((u8 *(*)(unsigned,unsigned,unsigned,unsigned))0x07f1bbb1)(0xfd03,task,4,n+6);
    m[0]=*(volatile u8 *)0x07fd2528;*(u16 *)(m+2)=6;*(u16 *)(m+4)=n;
    for(unsigned i=0;i<n;i++)m[6+i]=p[i];
    ((void (*)(void *))0x07f1bbe3)(m);
}
EXTRA static void entry(unsigned slot){
    u8 h[176];READ(addr(slot),176,h);volatile struct Entry *e=&R->entries[slot];
    e->token=get32(h+4);e->due=get32(h+8);e->next=e->due;e->last=0;e->zone=0;e->mask=0;e->check=1;e->duration=0;
    e->state=get32(h)==MAGIC?h[16]:255;
    if((h[20]==0xa5||h[20]==0xa6)&&(product_crc(0xffffffff,h+20,152)^0xffffffff)==get32(h+172)){
        e->mask=h[21];e->check=h[22];e->duration=h[23];e->zone=(i32)get32(h+24);
    }
}
EXTRA static void load(void){
    if(R->loaded)return;
    CALL0(0x07fc42e8);for(unsigned i=0;i<8;i++)entry(i);
    R->writing=0;R->trigger=255;R->last_slot=255;R->alert=255;R->loaded=1;
}
MAIN int product_reminder_cmd(const u8 *message,unsigned n){
    const u8 *p=message+6;unsigned command=p[0];
    if(command<0xb0||command>0xbc)return 1;
    if(S[8]||*(volatile u32 *)0x07fd0564)return 2;
    if(command==0xbc){
        if(n!=1)return 1;
        if(S[7]==1||R->writing)return 2;
        u8 b[16]={'E','F','D','1',1,128};CALL0(0x07fc42e8);
        unsigned id=((unsigned (*)(void))0x07fc6891)();b[6]=id;b[7]=id>>8;
        if(READ(0x40000,4,b+8)!=4||READ(0x7fffc,4,b+12)!=4)return 1;
        product_publish(b,16);return 0;
    }
    load();CALL0(0x07fc42e8);
    if(command==0xb3){if(n!=5)return 1;i32 off=(i32)get32(p+1);if(off< -50400||off>50400)return 1;R->offset=off;R->offset_valid=1;return 0;}
    if(command==0xb9){if(n!=1||!(S[27]&1)||!R->offset_valid)return 1;R->alert=255;R->hash=0;S[7]=5;summary(utc());return 0;}
    if(command==0xb8){
        if(!R->writing||n<3||n>20||p[1]!=R->meta_received||p[1]+n-2>156)return 1;
        product_flash_write(addr(R->slot)+20+p[1],p+2,n-2);R->meta_received+=n-2;R->age=0;return 0;
    }
    if(command==0xb6){if(n!=1)return 1;R->writing=0;return 0;}
    if(command==0xb0){
        if(n!=14||p[1]>=8||!get32(p+2)||get32(p+6)<1577836800u||get32(p+6)>2587680000u)return 1;
        unsigned slot=p[1];if(R->entries[slot].state==READY)return 2;
        R->writing=0;ERASE(addr(slot),8192);R->entries[slot].state=255;
        R->slot=slot;R->token=get32(p+2);R->due=get32(p+6);R->expected=get32(p+10);R->product_crc=0xffffffff;R->received=0;
        u8 h[20];for(unsigned i=0;i<20;i++)h[i]=255;put32(h+4,R->token);put32(h+8,R->due);put32(h+12,R->expected);product_flash_write(addr(slot),h,20);
        R->age=0;R->meta_received=0;R->writing=1;return 0;
    }
    if(command==0xb1){
        if(n<4||n>20||!R->writing)return 1;unsigned off=p[1]|(p[2]<<8),count=n-3;
        if(off!=R->received||off+count>8000)return 1;
        product_flash_write(addr(R->slot)+192+off,p+3,count);R->product_crc=product_crc(R->product_crc,p+3,count);R->received+=count;R->age=0;return 0;
    }
    if(command==0xb2){
        if(n!=5||!R->writing||get32(p+1)!=R->token||R->received!=8000||(R->product_crc^0xffffffff)!=R->expected)return 1;
        u8 b[64];u32 c=0xffffffff;
        for(unsigned off=0;off<8000;off+=64){READ(addr(R->slot)+192+off,64,b);c=product_crc(c,b,64);}
        if((c^0xffffffff)!=R->expected)return 1;
        if(R->meta_received){
            u8 h[156];READ(addr(R->slot)+20,156,h);
            if(R->meta_received!=156||(h[0]!=0xa5&&h[0]!=0xa6)||h[1]>127||(h[2]!=1&&h[2]!=5&&h[2]!=15&&h[2]!=60)||h[3]>120||
                (i32)get32(h+4)< -50400||(i32)get32(h+4)>50400||(product_crc(0xffffffff,h,152)^0xffffffff)!=get32(h+152))return 1;
        }
        put32(b,MAGIC);product_flash_write(addr(R->slot),b,4);b[0]=READY;product_flash_write(addr(R->slot)+16,b,1);
        entry(R->slot);if(R->entries[R->slot].mask){R->entries[R->slot].next=occurrence(&R->entries[R->slot],R->due);R->entries[R->slot].last=1;}R->writing=0;R->hash=0;return 0;
    }
    if(n<2||p[1]>=8)return 1;unsigned slot=p[1];
    if(command==0xbb){
        if(n!=2)return 1;volatile struct Entry *e=&R->entries[slot];u8 b[20]={69,82,77,50};
        b[4]=e->mask;b[5]=e->check;b[6]=e->duration;READ(addr(slot)+20,1,b+7);
        put32(b+8,e->next);put32(b+12,e->last);put32(b+16,e->zone);product_publish(b,20);return 0;
    }
    if(command==0xb5){
        if(n!=6||R->entries[slot].token!=get32(p+2))return 1;
        u8 state=CANCELLED;product_flash_write(addr(slot)+16,&state,1);R->entries[slot].state=state;R->hash=0;return 0;
    }
    if(command==0xb4){
        if(n!=2)return 1;u8 b[24]={69,82,77,49,1,0,0,0};b[5]=slot;b[6]=R->entries[slot].state;b[7]=R->writing|((R->last_slot+1)<<4);
        put32(b+8,R->entries[slot].token);put32(b+12,R->entries[slot].due);READ(addr(slot)+12,4,b+16);b[20]=R->received;b[21]=R->received>>8;b[22]=R->slot;b[23]=R->offset_valid;product_publish(b,24);return 0;
    }
    if(command==0xb7||command==0xba){
        if(n!=4)return 1;unsigned off=p[2]|(p[3]<<8);unsigned limit=command==0xba?156:8000;if(off>=limit)return 1;unsigned count=limit-off;if(count>128)count=128;
        u8 b[128];READ(addr(slot)+(command==0xba?20:192)+off,count,b);product_publish(b,count);return 0;
    }
    return 1;
}
EXTRA static u32 utc(void){
    unsigned year=G[2],days=0;for(unsigned y=1970;y<year;y++)days+=365+(!(y&3));
    static const u8 dm[12]={31,28,31,30,31,30,31,31,30,31,30,31};
    for(unsigned m=0;m<E[7];m++)days+=dm[m]+(m==1&&!(year&3));days+=E[8];
    i32 offset=(S[27]&2)?((S[27]&4)?7200:3600):R->offset;
    return days*86400u+E[9]*3600+E[10]*60-offset;
}
/* A fixed civil UTC offset belongs to each schedule, independently of the clock's NL zone.
   Retained last/next survive normal sleep. After complete power loss, repeating
   schedules resume at the next occurrence after calibration, without replaying missed doses. */
EXTRA static u32 occurrence(volatile struct Entry *e,u32 t){
    if(!e->mask)return e->due;
    if(t<e->due)t=e->due;
    u32 local=t+e->zone,day=DIV(local,86400),origin=e->due+e->zone;
    u32 tod=origin-DIV(origin,86400)*86400;
    for(unsigned i=0;i<8;i++,day++){
        unsigned w=day+4;w-=DIV(w,7)*7;u32 candidate=day*86400+tod-e->zone;
        if((e->mask&(1<<w))&&candidate>=t)return candidate;
    }return 0xffffffff;
}
EXTRA static void dot(int x,int y){unsigned pos=(249-x)*16+(y>>3),mask=128>>(y&7);BW[pos]&=~mask;}
EXTRA void product_frame_refresh(void){CALL0(LEDS_OFF);CALL0(0x07fc3f04);CALL0(0x07fc3f68);CALL0(0x07fc40e8);CALL0(0x07fc4174);CALL0(0x07fd1480);}
EXTRA static void summary(u32 t){
    char text[32];u8 title[144];u8 rows[8];unsigned count=0,waiting=0;
    u32 day=DIV(t+R->offset,86400),times[8];
    for(unsigned i=0;i<8;i++){
        volatile struct Entry *e=&R->entries[i];if(e->state!=READY&&e->state!=FIRED)continue;
        u32 due=e->mask?occurrence(e,day*86400-R->offset):e->due;
        if(DIV(due+R->offset,86400)!=day)continue;
        if(e->state==READY&&e->last!=due&&(!e->mask||e->next<=due))waiting++;
        unsigned j=count++;while(j&&times[j-1]>due){rows[j]=rows[j-1];times[j]=times[j-1];j--;}
        rows[j]=i;times[j]=due;
    }
    for(unsigned i=0;i<4000;i++){BW[i]=255;RR[i]=0;}
    product_ink(0x07fca48c,8,1,"今日任务",1);product_battery(194,4,1);G[14]=0x07fc7eb4;
    for(unsigned x=8;x<244;x++)dot(x,23);
    if(!count)TEXT(89,55,"今日无任务");
    /* ponytail: four sorted rows; remaining count is shown below, add paging only if required. */
    for(unsigned row=0;row<count&&row<4;row++){
        unsigned slot=rows[row],ry=(count>3?27:29)+row*(count>3?20:24);volatile struct Entry *e=&R->entries[slot];u32 when=times[row]+R->offset;
        unsigned minutes=DIV(when,60);minutes-=DIV(minutes,1440)*1440;
        FORMAT(text,"%02u:%02u",DIV(minutes,60),minutes-DIV(minutes,60)*60);product_ink(0x07fca48c,8,ry,text,1);
        u8 marker;READ(addr(slot)+20,1,&marker);
        if(marker==0xa5||marker==0xa6){unsigned h=marker==0xa6?16:12,w=marker==0xa6?72:96;READ(addr(slot)+28,144,title);for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++)if(title[y*(w>>3)+(x>>3)]&(128>>(x&7)))dot(68+x,ry+1+y);}
        else {FORMAT(text,"任务%u",slot+1);TEXT(68,ry+3,text);}
        TEXT(208,ry+3,(e->state==FIRED||e->last==times[row])?"已提醒":(e->mask&&e->next>times[row]&&times[row]<t)?"已过时":"待提醒");
    }
    unsigned y=1970,days=day;while(days>=365+(!(y&3))){days-=365+(!(y&3));y++;}
    static const u8 dm[12]={31,28,31,30,31,30,31,31,30,31,30,31};unsigned m=0;
    while(days>=dm[m]+(m==1&&!(y&3))){days-=dm[m]+(m==1&&!(y&3));m++;}
    for(unsigned x=8;x<244;x++)dot(x,106);
    FORMAT(text,"%u/%02u/%02u",y,m+1,days+1);G[14]=0x07fc90a4;TEXT(162,108,text);G[14]=0x07fc7eb4;
    if(count>4)FORMAT(text,"另有%u项",count-4);else FORMAT(text,"待提醒%u项",waiting);TEXT(8,110,text);
    u32 hash=product_crc(product_crc(0xffffffff,BW,4000),RR,4000);if(hash==R->hash)return;
    R->hash=hash;product_frame_refresh();
}
EXTRA int product_reminder_tick(void){
    load();if(R->writing){if(++R->age>=3)R->writing=0;return 1;}
    if(!R->offset_valid)return 0;u32 t=utc();
    if(R->alert!=255){
        unsigned slot=R->alert;
        if(S[7]!=2||*(volatile u16 *)(S+12)!=(u16)R->entries[slot].token)R->alert=255;
        else if(R->expiry&&t<R->expiry)return 1;
        else if(R->expiry){R->alert=255;if(!product_album_restore())S[7]=5;R->hash=0;}
    }
    unsigned slot=8;u32 first=0xffffffff;
    for(unsigned i=0;i<8;i++){
        volatile struct Entry *e=&R->entries[i];if(e->state!=READY)continue;
        if(e->mask&&!e->last&&e->next<=t){e->next=occurrence(e,t);e->last=1;}
        unsigned minute=DIV(t+e->zone,60);
        if(e->next<=t&&!(minute-DIV(minute,e->check)*e->check)&&e->next<first){slot=i;first=e->next;}
    }
    if(slot==8&&S[7]!=5)return 0;
    CALL0(0x07fc42e8);if(slot==8){summary(t);return 1;}
    READ(addr(slot)+192,4000,BW);READ(addr(slot)+4192,4000,RR);
    u8 b[4];READ(addr(slot)+12,4,b);u32 c=product_crc(product_crc(0xffffffff,BW,4000),RR,4000)^0xffffffff;
    if(c!=get32(b)){b[0]=CANCELLED;product_flash_write(addr(slot)+16,b,1);R->entries[slot].state=CANCELLED;S[9]=5;return 0;}
    for(unsigned y=8;y<=22;y++)for(unsigned x=176;x<250;x++){unsigned pos=(249-x)*16+(y>>3),mask=128>>(y&7);BW[pos]|=mask;RR[pos]&=~mask;}
    product_battery(194,10,1);R->trigger=slot;S[7]=2;S[9]=0;*(volatile u16 *)(S+12)=R->entries[slot].token;
    product_frame_refresh();return 1;
}
EXTRA void product_reminder_finish(void){
    if(S[9]==4)R->hash=0;
    if(!R->loaded||R->trigger==255)return;unsigned slot=R->trigger;volatile struct Entry *e=&R->entries[slot];
    if(S[9]==4||!e->mask){u8 state=S[9]==4?CANCELLED:FIRED;CALL0(0x07fc42e8);product_flash_write(addr(slot)+16,&state,1);e->state=state;}
    if(S[9]!=4){e->last=e->next;if(e->mask)e->next=occurrence(e,utc()+1);R->last_slot=slot;R->alert=slot;R->expiry=e->duration?utc()+e->duration*60:0;}
    R->trigger=255;
}
