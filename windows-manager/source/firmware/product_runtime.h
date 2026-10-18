#ifndef ELINK_PRODUCT_RUNTIME_H
#define ELINK_PRODUCT_RUNTIME_H
/* Exact DA14585 five-pad / IL3897 BWR baseline. No heap, SDK or libc dependency. */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
#define S ((volatile u8 *)0x07fd1980)
#define E ((volatile u32 *)0x07fd04dc)
#define G ((volatile u32 *)0x07fcdd98)
#define BW ((u8 *)0x07fcdedc)
#define RR ((u8 *)0x07fcf15c)
#define CALL0(a) ((void (*)(void))((a)|1))()
#define TEXT ((void (*)(int,int,const char *))0x07fc3b4d)
#define FORMAT ((int (*)(char *,const char *,...))0x07fc7051)
#define CMD1 ((void (*)(int,int))0x07fc3c11)
#define CMD2 ((void (*)(int,int,int))0x07fc3c49)
#define CMD3 ((void (*)(int,int,int,int))0x07fc3c85)
#define CMD ((void (*)(int))0x07fc3be9)
#define DATA ((void (*)(const u8 *,int))0x07fc3cf5)
#define DIV ((u32 (*)(u32,u32))0x07f1dfb9)
/* Native tables: 12/14/18/15px; photo 44px and original clock 66px use lossless run coding. */
#define SMALL 0x07fc7eb4
#define DATE 0x07fc90a4
#define MAIN 0x07fca48c
#define DAYS 0x07fcc2a0
#define PHOTO_DAYS 0x07fcb780
#define DIGITS 0x07fcc3c4
/* This former, unused low-resolution font lives in the retained application RAM. */
struct Ui {u32 outside,red,pending_outside,pending_red,date,pending_date;
    u8 valid,pending,partial,hour,pending_hour,count,ticks,view;};
#define U ((volatile struct Ui *)0x07fca46c)
__attribute__((used)) const u8 product_caps[8]={'E','L','U','I',1,255,15,0};
extern int product_reminder_cmd(const u8 *,unsigned);
extern int product_reminder_tick(void);
extern void product_reminder_finish(void);
extern int product_album_cmd(const u8 *,unsigned);
extern void product_album_init(void);
extern int product_album_tick(void);
extern void product_album_finish(void);
extern void product_frame_refresh(void);
int product_control(const u8 *packet,unsigned length);
#endif
